"""
CityScout — Personalized city guides powered by RAG.
FastAPI backend with Pinecone vector search, OpenAI embeddings & generation, and RAGAS evaluation.
"""

import json, os, re, time, threading, glob
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from pydantic import BaseModel
from typing import Optional

from prompts import (
    PROFILE_SYSTEM_PROMPT,
    PROFILE_USER_TEMPLATE,
    GUIDE_SYSTEM_PROMPT,
    GUIDE_USER_TEMPLATE,
)

# ── Config ──

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

CITIES_DIR = BASE_DIR / "data" / "cities"
INDEX = os.getenv("PINECONE_INDEX", "cityscout-rag")
EMBEDDING_MODEL = "openai/text-embedding-3-small"
CHAT_MODEL = "openai/gpt-4o-mini"

openai_client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

app = FastAPI(title="CityScout RAG API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ingest_state = {
    "running": False,
    "phase": "idle",
    "total": 0,
    "processed": 0,
    "error": None,
}

# ── Pydantic Models ──


class QuizAnswers(BaseModel):
    coffee: str
    food: str
    activity: str
    nightlife: str
    neighborhood: str
    budget: str


class ProfileRequest(BaseModel):
    quiz_answers: QuizAnswers


class GuideRequest(BaseModel):
    profile: str
    city: str
    top_k: int = 8


# ── Helpers ──


def get_available_cities() -> list[dict]:
    """Scan data/cities/ for JSON files and return city metadata."""
    cities = []
    if not CITIES_DIR.exists():
        return cities
    for fp in sorted(CITIES_DIR.glob("*.json")):
        slug = fp.stem
        name = slug.replace("-", " ").title()
        try:
            data = json.loads(fp.read_text())
            chunk_count = len(data)
            categories = sorted(set(item.get("category", "") for item in data))
        except Exception:
            chunk_count = 0
            categories = []
        cities.append(
            {
                "slug": slug,
                "name": name,
                "chunk_count": chunk_count,
                "categories": categories,
            }
        )
    return cities


def embed_text(text: str) -> list[float]:
    """Create an embedding vector for a single text string."""
    resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Create embedding vectors for a batch of texts."""
    resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def chunk_text(text: str, max_words: int = 400, overlap: int = 50) -> list[str]:
    """Split text into overlapping word-level chunks if needed."""
    words = text.split()
    if len(words) <= max_words:
        return [text] if words else []
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + max_words]))
        i += max_words - overlap
    return chunks


def load_city_data(city_slug: str) -> list[dict]:
    """Load city data from JSON file, chunking long texts."""
    fp = CITIES_DIR / f"{city_slug}.json"
    if not fp.exists():
        raise FileNotFoundError(f"No data file for city: {city_slug}")
    raw = json.loads(fp.read_text())
    chunks = []
    for item in raw:
        text = item.get("text", "")
        if len(text.split()) <= 500:
            # Single chunk — include metadata in the text for richer embedding
            embed_text_str = (
                f"City: {item.get('city', '')}\n"
                f"Category: {item.get('category', '')}\n"
                f"Source: {item.get('source_type', '')} — {item.get('source_url', '')}\n\n"
                f"{text}"
            )
            chunks.append(
                {
                    "id": item.get("id", f"{city_slug}-{len(chunks)}"),
                    "text": embed_text_str,
                    "metadata": {
                        "city": item.get("city", city_slug),
                        "category": item.get("category", "general"),
                        "source_url": item.get("source_url", ""),
                        "source_type": item.get("source_type", ""),
                        "date": item.get("date", ""),
                        "text": text[:3500],
                    },
                }
            )
        else:
            # Split into sub-chunks
            for ci, c in enumerate(chunk_text(text)):
                chunks.append(
                    {
                        "id": f"{item.get('id', city_slug)}-{ci}",
                        "text": (
                            f"City: {item.get('city', '')}\n"
                            f"Category: {item.get('category', '')}\n"
                            f"Source: {item.get('source_type', '')} — {item.get('source_url', '')}\n\n"
                            f"{c}"
                        ),
                        "metadata": {
                            "city": item.get("city", city_slug),
                            "category": item.get("category", "general"),
                            "source_url": item.get("source_url", ""),
                            "source_type": item.get("source_type", ""),
                            "date": item.get("date", ""),
                            "text": c[:3500],
                        },
                    }
                )
    return chunks


# ── RAGAS Evaluation ──

_ragas_cache = {}


def get_ragas_evaluator():
    """Lazy-init RAGAS evaluator (reused across requests)."""
    if not _ragas_cache:
        from ragas.llms import llm_factory
        from ragas.embeddings import embedding_factory

        _ragas_cache["llm"] = llm_factory("gpt-4o-mini")
        _ragas_cache["emb"] = embedding_factory("text-embedding-3-small")
        print("[ragas] Evaluator initialized (gpt-4o-mini + text-embedding-3-small)")
    return _ragas_cache["llm"], _ragas_cache["emb"]


def score_with_ragas(question: str, answer: str, contexts: list[str]) -> dict:
    """
    Evaluate a RAG result with RAGAS metrics:
    - Faithfulness: is the answer grounded in retrieved contexts?
    - ContextPrecision: are the retrieved chunks relevant?
    - ResponseRelevancy: does the answer address the question?
    """
    from ragas import SingleTurnSample, EvaluationDataset, evaluate
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference, ResponseRelevancy

    evaluator_llm, evaluator_emb = get_ragas_evaluator()

    sample = SingleTurnSample(
        user_input=question,
        response=answer,
        retrieved_contexts=contexts,
    )
    result = evaluate(
        dataset=EvaluationDataset(samples=[sample]),
        metrics=[
            Faithfulness(),
            LLMContextPrecisionWithoutReference(),
            ResponseRelevancy(),
        ],
        llm=evaluator_llm,
        embeddings=evaluator_emb,
    )

    df = result.to_pandas()
    precision_col = next((c for c in df.columns if "precision" in c.lower()), None)
    relevancy_col = next((c for c in df.columns if "relevancy" in c.lower()), None)

    return {
        "faithfulness": round(float(df["faithfulness"].iloc[0]), 3),
        "context_precision": (
            round(float(df[precision_col].iloc[0]), 3) if precision_col else None
        ),
        "relevancy": (
            round(float(df[relevancy_col].iloc[0]), 3) if relevancy_col else None
        ),
    }


def _score_label(val):
    if val is None:
        return "N/A"
    if val >= 0.8:
        return f"{val:.3f} ✓ GOOD"
    if val >= 0.5:
        return f"{val:.3f} ~ OK"
    return f"{val:.3f} ✗ LOW"


# ── Ingestion ──


def run_ingestion():
    """Ingest all city data files into Pinecone."""
    global ingest_state
    try:
        ingest_state["phase"] = "loading"
        print("[ingest] Loading city data files...")

        all_chunks = []
        city_files = list(CITIES_DIR.glob("*.json"))
        if not city_files:
            raise FileNotFoundError(f"No city data files found in {CITIES_DIR}")

        for fp in city_files:
            city_slug = fp.stem
            print(f"[ingest] Loading {city_slug}...")
            chunks = load_city_data(city_slug)
            all_chunks.extend(chunks)
            print(f"[ingest]   → {len(chunks)} chunks from {city_slug}")

        print(f"[ingest] Total: {len(all_chunks)} chunks across {len(city_files)} cities")
        ingest_state["total"] = len(all_chunks)

        # Ensure Pinecone index exists
        ingest_state["phase"] = "indexing"
        existing = [idx.name for idx in pc.list_indexes()]
        if INDEX not in existing:
            print(f"[ingest] Creating Pinecone index '{INDEX}'...")
            pc.create_index(
                name=INDEX,
                dimension=1536,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            # Wait for index to be ready
            print("[ingest] Waiting for index to be ready...")
            time.sleep(30)

        idx = pc.Index(INDEX)

        # Embed + upsert in batches
        ingest_state["phase"] = "embedding"
        batch_size = 50
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]
            texts = [c["text"] for c in batch]

            print(f"[ingest] Embedding batch {i//batch_size + 1}...")
            embeddings = embed_batch(texts)

            vectors = [
                {
                    "id": c["id"],
                    "values": emb,
                    "metadata": c["metadata"],
                }
                for c, emb in zip(batch, embeddings)
            ]

            idx.upsert(vectors=vectors)
            ingest_state["processed"] = min(i + batch_size, len(all_chunks))
            print(
                f"[ingest] {ingest_state['processed']}/{len(all_chunks)} vectors upserted"
            )
            time.sleep(0.3)  # Rate limit courtesy

        ingest_state.update(phase="done", running=False)
        print(f"[ingest] ✓ Done — {len(all_chunks)} vectors indexed")

    except Exception as e:
        print(f"[ingest] Error: {e}")
        import traceback
        traceback.print_exc()
        ingest_state.update(phase="error", error=str(e), running=False)


# ── Routes ──


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cityscout-rag"}


@app.get("/api/cities")
def list_cities():
    """Return list of available cities with metadata."""
    cities = get_available_cities()
    return {"cities": cities}


@app.post("/api/ingest")
def ingest():
    """Start background ingestion of all city data into Pinecone."""
    if ingest_state["running"]:
        raise HTTPException(409, "Ingestion already running")
    ingest_state.update(running=True, phase="loading", total=0, processed=0, error=None)
    threading.Thread(target=run_ingestion, daemon=True).start()
    return {"message": "Ingestion started", "state": ingest_state}


@app.get("/api/ingest/status")
def ingestion_status():
    return ingest_state


@app.post("/api/profile")
def generate_profile(req: ProfileRequest):
    """Generate a taste profile from quiz answers using LLM."""
    t_start = time.time()
    print(f"\n{'='*70}")
    print(f"[profile] Generating taste profile from quiz answers")
    print(f"{'─'*70}")

    answers = req.quiz_answers
    print(f"  Coffee: {answers.coffee}")
    print(f"  Food: {answers.food}")
    print(f"  Activity: {answers.activity}")
    print(f"  Nightlife: {answers.nightlife}")
    print(f"  Neighborhood: {answers.neighborhood}")
    print(f"  Budget: {answers.budget}")

    user_prompt = PROFILE_USER_TEMPLATE.format(
        coffee=answers.coffee,
        food=answers.food,
        activity=answers.activity,
        nightlife=answers.nightlife,
        neighborhood=answers.neighborhood,
        budget=answers.budget,
    )

    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": PROFILE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=300,
    )

    profile = completion.choices[0].message.content.strip()
    elapsed = time.time() - t_start

    print(f"  → Profile: {profile[:100]}...")
    print(f"  → Generated in {elapsed:.2f}s")
    print(f"{'='*70}\n")

    return {
        "profile": profile,
        "usage": {
            "prompt_tokens": completion.usage.prompt_tokens,
            "completion_tokens": completion.usage.completion_tokens,
            "total_tokens": completion.usage.total_tokens,
        },
    }


@app.post("/api/guide")
def generate_guide(req: GuideRequest):
    """
    Main RAG pipeline:
    1. Embed user profile as query
    2. Query Pinecone for city-specific knowledge
    3. Generate personalized guide with citations
    4. Evaluate with RAGAS
    """
    t_start = time.time()
    print(f"\n{'='*70}")
    print(f"[guide] Generating personalized guide")
    print(f"[guide] City: {req.city} | top_k: {req.top_k}")
    print(f"[guide] Profile: {req.profile[:80]}...")
    print(f"{'─'*70}")

    # ── Step 1: Build profile-aware queries ──
    categories = ["coffee", "food", "nightlife", "culture", "neighborhoods", "fitness"]
    query_text = f"Travel recommendations for someone with this taste profile: {req.profile}. City: {req.city}"

    print("[1/4 EMBED] Creating query embedding...")
    t1 = time.time()
    query_vec = embed_text(query_text)
    t_embed = time.time() - t1
    print(f"  → Embedding: {t_embed:.2f}s | dim={len(query_vec)}")

    # ── Step 2: Retrieve from Pinecone ──
    print(f"[2/4 RETRIEVE] Querying Pinecone index '{INDEX}'...")
    t2 = time.time()

    try:
        idx = pc.Index(INDEX)
        results = idx.query(
            vector=query_vec,
            top_k=req.top_k,
            include_metadata=True,
            filter={"city": {"$eq": req.city.lower().replace(" ", "-")}},
        )
        matches = results.matches
    except Exception as e:
        print(f"  → Pinecone query failed: {e}")
        raise HTTPException(500, f"Vector search failed: {str(e)}")

    t_search = time.time() - t2
    print(f"  → Search: {t_search:.2f}s | {len(matches)} chunks retrieved")

    # Also do category-specific queries for diversity
    all_matches = {m.id: m for m in matches}
    for cat in ["coffee", "food", "nightlife", "culture"]:
        cat_query = f"{req.profile}. Best {cat} recommendations in {req.city}"
        cat_vec = embed_text(cat_query)
        try:
            cat_results = idx.query(
                vector=cat_vec,
                top_k=3,
                include_metadata=True,
                filter={"city": {"$eq": req.city.lower().replace(" ", "-")}},
            )
            for m in cat_results.matches:
                if m.id not in all_matches:
                    all_matches[m.id] = m
        except Exception:
            pass

    final_matches = sorted(all_matches.values(), key=lambda m: m.score, reverse=True)
    print(f"  → After diversity expansion: {len(final_matches)} unique chunks")

    # Log retrieved chunks
    sources = []
    total_ctx_chars = 0
    print(f"  {'─'*66}")
    for i, m in enumerate(final_matches):
        text = m.metadata.get("text", "")
        chars = len(text)
        total_ctx_chars += chars
        preview = text[:80].replace("\n", " ")
        source = {
            "score": m.score,
            "text": text,
            "category": m.metadata.get("category", ""),
            "source_url": m.metadata.get("source_url", ""),
            "source_type": m.metadata.get("source_type", ""),
            "city": m.metadata.get("city", ""),
            "date": m.metadata.get("date", ""),
        }
        sources.append(source)
        print(f"  [{i+1}] score={m.score:.4f} | {chars:,} chars | cat={source['category']}")
        print(f"      src: {source['source_type']} — {source['source_url'][:60]}")
        print(f"      text: \"{preview}...\"")
    print(f"  {'─'*66}")
    print(f"  Total context: {total_ctx_chars:,} chars across {len(sources)} chunks")

    # ── Step 3: Generate guide ──
    print(f"{'─'*70}")
    print("[3/4 GENERATE] Sending to LLM...")

    context = "\n\n---\n\n".join(
        f"[{i+1}] Category: {s['category']} | Source: {s['source_type']} — {s['source_url']}\n{s['text']}"
        for i, s in enumerate(sources)
    )
    user_prompt = GUIDE_USER_TEMPLATE.format(
        profile=req.profile,
        city=req.city.replace("-", " ").title(),
        context=context,
    )

    print(f"  → System prompt: {len(GUIDE_SYSTEM_PROMPT)} chars")
    print(f"  → User prompt: {len(user_prompt):,} chars")

    t3 = time.time()
    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": GUIDE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=3000,
    )
    t_gen = time.time() - t3

    guide = completion.choices[0].message.content
    tokens = completion.usage
    print(f"  → LLM responded in {t_gen:.2f}s | model={CHAT_MODEL}")
    print(f"  → Tokens: prompt={tokens.prompt_tokens:,} + completion={tokens.completion_tokens:,} = {tokens.total_tokens:,}")
    print(f"  → Guide length: {len(guide):,} chars")
    for line in guide.split("\n")[:5]:
        print(f"  │ {line[:90]}")
    if guide.count("\n") > 5:
        print(f"  │ ... ({guide.count(chr(10)) - 5} more lines)")

    # ── Step 4: RAGAS Evaluation ──
    print(f"{'─'*70}")
    print("[4/4 RAGAS] Evaluating retrieval + generation quality...")
    contexts_for_eval = [s["text"] for s in sources]
    t4 = time.time()
    try:
        scores = score_with_ragas(
            f"Personalized {req.city} guide for: {req.profile[:200]}",
            guide,
            contexts_for_eval,
        )
        t_ragas = time.time() - t4
        print(f"  → Completed in {t_ragas:.2f}s")
        print(f"  ┌────────────────────────────────────────────┐")
        print(f"  │  Faithfulness:      {_score_label(scores['faithfulness']):>20} │")
        print(f"  │  Context Precision: {_score_label(scores['context_precision']):>20} │")
        print(f"  │  Relevancy:         {_score_label(scores['relevancy']):>20} │")
        print(f"  └────────────────────────────────────────────┘")
    except Exception as e:
        t_ragas = time.time() - t4
        print(f"  → RAGAS evaluation failed in {t_ragas:.2f}s: {e}")
        scores = {"error": str(e), "faithfulness": None, "context_precision": None, "relevancy": None}

    # ── Summary ──
    total = time.time() - t_start
    print(f"{'─'*70}")
    print(f"[summary] embed={t_embed:.2f}s → search={t_search:.2f}s → generate={t_gen:.2f}s → ragas={t_ragas:.2f}s")
    print(f"[summary] Total: {total:.2f}s | {tokens.total_tokens:,} tokens | {len(sources)} sources")
    print(f"{'='*70}\n")

    return {
        "guide": guide,
        "sources": sources,
        "scores": scores,
        "city": req.city,
        "usage": {
            "prompt_tokens": tokens.prompt_tokens,
            "completion_tokens": tokens.completion_tokens,
            "total_tokens": tokens.total_tokens,
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", "3001"))
    print(f"CityScout RAG API → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
