"""
CityScout — Personalized city guides powered by RAG.
FastAPI backend with Pinecone vector search, OpenAI embeddings & generation,
multi-source user data upload, dual-corpus RAG, and RAGAS evaluation.
"""

import json, os, re, time, threading, glob, uuid
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
    ENHANCED_PROFILE_SYSTEM_PROMPT,
    ENHANCED_PROFILE_USER_TEMPLATE,
    ENHANCED_GUIDE_SYSTEM_PROMPT,
    ENHANCED_GUIDE_USER_TEMPLATE,
)
from parsers import parse_user_data, PARSERS

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
    user_id: Optional[str] = None  # If set, also query user namespace for dual-corpus RAG


class UserDataUpload(BaseModel):
    source: str   # "spotify" | "youtube" | "google_maps" | "instagram"
    data: dict    # Raw export JSON
    user_id: Optional[str] = None  # Auto-generated if not provided


# In-memory user data store (maps user_id → uploaded source info)
user_data_store: dict[str, dict] = {}


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
    """Evaluate a RAG result with RAGAS metrics."""
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
            print("[ingest] Waiting for index to be ready...")
            time.sleep(30)

        idx = pc.Index(INDEX)

        ingest_state["phase"] = "embedding"
        batch_size = 50
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]
            texts = [c["text"] for c in batch]

            print(f"[ingest] Embedding batch {i//batch_size + 1}...")
            embeddings = embed_batch(texts)

            vectors = [
                {"id": c["id"], "values": emb, "metadata": c["metadata"]}
                for c, emb in zip(batch, embeddings)
            ]

            idx.upsert(vectors=vectors)
            ingest_state["processed"] = min(i + batch_size, len(all_chunks))
            print(f"[ingest] {ingest_state['processed']}/{len(all_chunks)} vectors upserted")
            time.sleep(0.3)

        ingest_state.update(phase="done", running=False)
        print(f"[ingest] ✓ Done — {len(all_chunks)} vectors indexed")

    except Exception as e:
        print(f"[ingest] Error: {e}")
        import traceback
        traceback.print_exc()
        ingest_state.update(phase="error", error=str(e), running=False)


# ── Routes: Core ──


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cityscout-rag"}


@app.get("/api/cities")
def list_cities():
    """Return list of available cities with metadata."""
    return {"cities": get_available_cities()}


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


# ── Routes: Profile (quiz-only) ──


@app.post("/api/profile")
def generate_profile(req: ProfileRequest):
    """Generate a taste profile from quiz answers using LLM."""
    t_start = time.time()
    print(f"\n{'='*70}")
    print(f"[profile] Generating taste profile from quiz answers")
    print(f"{'─'*70}")

    answers = req.quiz_answers
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


# ── Routes: User Data Upload ──


@app.post("/api/profile/upload")
def upload_user_data(req: UserDataUpload):
    """
    Upload user data from external platforms (Spotify, YouTube, Maps, Instagram).
    Parses the data, embeds it into Pinecone under a user-specific namespace,
    and returns parsed signals summary.
    """
    t_start = time.time()

    # Validate source
    if req.source not in PARSERS:
        raise HTTPException(400, f"Unknown source: {req.source}. Valid: {list(PARSERS.keys())}")

    # Generate or use provided user_id
    user_id = req.user_id or str(uuid.uuid4())[:8]
    namespace = f"user_{user_id}"

    print(f"\n{'='*70}")
    print(f"[upload] Processing {req.source} data for user {user_id}")
    print(f"[upload] Namespace: {namespace}")
    print(f"{'─'*70}")

    # Step 1: Parse
    print(f"[1/3 PARSE] Extracting signals from {req.source}...")
    try:
        signal_chunks = parse_user_data(req.source, req.data)
    except Exception as e:
        print(f"  → Parse error: {e}")
        raise HTTPException(400, f"Failed to parse {req.source} data: {str(e)}")

    print(f"  → Extracted {len(signal_chunks)} signal chunks")
    for i, chunk in enumerate(signal_chunks):
        print(f"  [{i+1}] {chunk['metadata']['signal_type']} / {chunk['metadata']['category']}: {chunk['text'][:80]}...")

    if not signal_chunks:
        return {
            "user_id": user_id,
            "source": req.source,
            "chunks_stored": 0,
            "message": "No preference signals extracted from this data",
        }

    # Step 2: Embed
    print(f"[2/3 EMBED] Creating embeddings for {len(signal_chunks)} chunks...")
    texts = [c["text"] for c in signal_chunks]
    embeddings = embed_batch(texts)

    # Step 3: Store in Pinecone user namespace
    print(f"[3/3 STORE] Upserting to Pinecone namespace '{namespace}'...")
    try:
        idx = pc.Index(INDEX)
        vectors = []
        for i, (chunk, emb) in enumerate(zip(signal_chunks, embeddings)):
            vectors.append({
                "id": f"{namespace}-{req.source}-{i}",
                "values": emb,
                "metadata": {
                    "text": chunk["text"][:3500],
                    "signal_type": chunk["metadata"]["signal_type"],
                    "category": chunk["metadata"]["category"],
                    "source_type": chunk["metadata"]["source_type"],
                    "user_id": user_id,
                },
            })

        idx.upsert(vectors=vectors, namespace=namespace)
        print(f"  → Upserted {len(vectors)} vectors to namespace '{namespace}'")

    except Exception as e:
        print(f"  → Pinecone error: {e}")
        raise HTTPException(500, f"Failed to store user data: {str(e)}")

    # Track uploaded sources per user
    if user_id not in user_data_store:
        user_data_store[user_id] = {"sources": [], "chunk_count": 0, "signals": []}
    user_data_store[user_id]["sources"].append(req.source)
    user_data_store[user_id]["chunk_count"] += len(vectors)
    user_data_store[user_id]["signals"].extend(signal_chunks)

    elapsed = time.time() - t_start
    print(f"  → Done in {elapsed:.2f}s")
    print(f"{'='*70}\n")

    return {
        "user_id": user_id,
        "source": req.source,
        "chunks_stored": len(vectors),
        "signal_types": list(set(c["metadata"]["signal_type"] for c in signal_chunks)),
        "categories": list(set(c["metadata"]["category"] for c in signal_chunks)),
        "signals": [
            {
                "type": c["metadata"]["signal_type"],
                "category": c["metadata"]["category"],
                "preview": c["text"][:120],
            }
            for c in signal_chunks
        ],
    }


@app.get("/api/profile/user/{user_id}")
def get_user_data_status(user_id: str):
    """Get status of uploaded user data."""
    info = user_data_store.get(user_id)
    if not info:
        raise HTTPException(404, f"No data found for user {user_id}")
    return {
        "user_id": user_id,
        "sources": list(set(info["sources"])),
        "chunk_count": info["chunk_count"],
        "namespace": f"user_{user_id}",
    }


# ── Routes: Enhanced Profile (quiz + uploaded data) ──


@app.post("/api/profile/enhance")
def enhance_profile(req: dict):
    """
    Generate an enhanced profile by combining quiz answers with uploaded user data signals.
    Requires: quiz_answers (dict), user_id (str).
    """
    quiz_answers = req.get("quiz_answers", {})
    user_id = req.get("user_id")

    if not user_id or user_id not in user_data_store:
        raise HTTPException(400, "No user data uploaded. Upload data first or use /api/profile.")

    t_start = time.time()
    print(f"\n{'='*70}")
    print(f"[enhance] Generating enhanced profile for user {user_id}")
    print(f"{'─'*70}")

    # Retrieve user signal chunks from Pinecone
    namespace = f"user_{user_id}"
    try:
        idx = pc.Index(INDEX)
        query_vec = embed_text("user preferences music food culture nightlife")
        results = idx.query(
            vector=query_vec,
            top_k=20,
            include_metadata=True,
            namespace=namespace,
        )
        user_signals = [m.metadata.get("text", "") for m in results.matches]
    except Exception as e:
        print(f"  → Error fetching user signals: {e}")
        user_signals = []

    print(f"  → Retrieved {len(user_signals)} user signal chunks")

    user_prompt = ENHANCED_PROFILE_USER_TEMPLATE.format(
        coffee=quiz_answers.get("coffee", "Not specified"),
        food=quiz_answers.get("food", "Not specified"),
        activity=quiz_answers.get("activity", "Not specified"),
        nightlife=quiz_answers.get("nightlife", "Not specified"),
        neighborhood=quiz_answers.get("neighborhood", "Not specified"),
        budget=quiz_answers.get("budget", "Not specified"),
        user_data_signals="\n".join(f"- {s}" for s in user_signals) if user_signals else "No additional data.",
    )

    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": ENHANCED_PROFILE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=500,
    )

    profile = completion.choices[0].message.content.strip()
    elapsed = time.time() - t_start
    print(f"  → Enhanced profile: {profile[:100]}...")
    print(f"  → Generated in {elapsed:.2f}s")
    print(f"{'='*70}\n")

    return {
        "profile": profile,
        "enhanced": True,
        "user_id": user_id,
        "data_sources": list(set(user_data_store[user_id]["sources"])),
        "usage": {
            "prompt_tokens": completion.usage.prompt_tokens,
            "completion_tokens": completion.usage.completion_tokens,
            "total_tokens": completion.usage.total_tokens,
        },
    }


# ── Routes: Guide Generation (dual-corpus RAG) ──


@app.post("/api/guide")
def generate_guide(req: GuideRequest):
    """
    Main RAG pipeline with optional dual-corpus retrieval:
    1. Embed user profile as query
    2. Query Pinecone for city-specific knowledge (city corpus)
    3. If user_id provided, also query user profile corpus (user namespace)
    4. Generate personalized guide with citations
    5. Evaluate with RAGAS
    """
    t_start = time.time()
    has_user_data = req.user_id and req.user_id in user_data_store
    print(f"\n{'='*70}")
    print(f"[guide] Generating {'enhanced ' if has_user_data else ''}personalized guide")
    print(f"[guide] City: {req.city} | top_k: {req.top_k} | user_id: {req.user_id or 'none'}")
    print(f"[guide] Profile: {req.profile[:80]}...")
    print(f"{'─'*70}")

    # ── Step 1: Embed query ──
    query_text = f"Travel recommendations for someone with this taste profile: {req.profile}. City: {req.city}"
    print("[1/5 EMBED] Creating query embedding...")
    t1 = time.time()
    query_vec = embed_text(query_text)
    t_embed = time.time() - t1
    print(f"  → Embedding: {t_embed:.2f}s | dim={len(query_vec)}")

    # ── Step 2: Retrieve from city corpus ──
    print(f"[2/5 RETRIEVE-CITY] Querying Pinecone index '{INDEX}'...")
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
    print(f"  → City search: {t_search:.2f}s | {len(matches)} chunks retrieved")

    # Category-specific queries for diversity
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
    print(f"  → After diversity expansion: {len(final_matches)} unique city chunks")

    # ── Step 3: Retrieve from user corpus (if available) ──
    user_signals = []
    t_user = 0.0
    if has_user_data:
        user_namespace = f"user_{req.user_id}"
        print(f"[3/5 RETRIEVE-USER] Querying user namespace '{user_namespace}'...")
        t3u = time.time()
        try:
            user_results = idx.query(
                vector=query_vec,
                top_k=10,
                include_metadata=True,
                namespace=user_namespace,
            )
            for m in user_results.matches:
                user_signals.append({
                    "score": m.score,
                    "text": m.metadata.get("text", ""),
                    "signal_type": m.metadata.get("signal_type", ""),
                    "category": m.metadata.get("category", ""),
                    "source_type": m.metadata.get("source_type", ""),
                })
            t_user = time.time() - t3u
            print(f"  → User signals: {t_user:.2f}s | {len(user_signals)} chunks")
            for i, s in enumerate(user_signals):
                print(f"  [U{i+1}] score={s['score']:.4f} | {s['signal_type']}/{s['category']}")
        except Exception as e:
            t_user = time.time() - t3u
            print(f"  → User namespace query failed: {e} (continuing without user data)")
    else:
        print("[3/5 RETRIEVE-USER] No user_id — skipping user corpus")

    # Build city sources list
    sources = []
    total_ctx_chars = 0
    print(f"  {'─'*66}")
    for i, m in enumerate(final_matches):
        text = m.metadata.get("text", "")
        chars = len(text)
        total_ctx_chars += chars
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
    print(f"  {'─'*66}")
    print(f"  Total context: {total_ctx_chars:,} chars across {len(sources)} city chunks")

    # ── Step 4: Generate guide ──
    print(f"{'─'*70}")
    print("[4/5 GENERATE] Sending to LLM...")

    context = "\n\n---\n\n".join(
        f"[{i+1}] Category: {s['category']} | Source: {s['source_type']} — {s['source_url']}\n{s['text']}"
        for i, s in enumerate(sources)
    )

    # Choose prompt based on whether we have user data
    if has_user_data and user_signals:
        user_context = "\n\n".join(
            f"[{s['source_type'].upper()}] ({s['category']}/{s['signal_type']}): {s['text']}"
            for s in user_signals
        )
        user_prompt = ENHANCED_GUIDE_USER_TEMPLATE.format(
            profile=req.profile,
            city=req.city.replace("-", " ").title(),
            context=context,
            user_context=user_context,
        )
        system_prompt = ENHANCED_GUIDE_SYSTEM_PROMPT
        print(f"  → Using ENHANCED dual-corpus prompt (city + user data)")
    else:
        user_prompt = GUIDE_USER_TEMPLATE.format(
            profile=req.profile,
            city=req.city.replace("-", " ").title(),
            context=context,
        )
        system_prompt = GUIDE_SYSTEM_PROMPT
        print(f"  → Using standard single-corpus prompt")

    print(f"  → System prompt: {len(system_prompt)} chars")
    print(f"  → User prompt: {len(user_prompt):,} chars")

    t3 = time.time()
    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
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

    # ── Step 5: RAGAS Evaluation ──
    print(f"{'─'*70}")
    print("[5/5 RAGAS] Evaluating retrieval + generation quality...")
    contexts_for_eval = [s["text"] for s in sources]
    if user_signals:
        contexts_for_eval.extend([s["text"] for s in user_signals])

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
    print(f"[summary] embed={t_embed:.2f}s → city_search={t_search:.2f}s → user_search={t_user:.2f}s → generate={t_gen:.2f}s → ragas={t_ragas:.2f}s")
    print(f"[summary] Total: {total:.2f}s | {tokens.total_tokens:,} tokens | {len(sources)} city sources | {len(user_signals)} user signals")
    print(f"{'='*70}\n")

    return {
        "guide": guide,
        "sources": sources,
        "user_signals": user_signals if user_signals else None,
        "scores": scores,
        "city": req.city,
        "enhanced": bool(has_user_data and user_signals),
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
