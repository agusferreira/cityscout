"""
CityScout — Personalized city guides powered by RAG.
FastAPI backend with Pinecone vector search, OpenAI embeddings & generation,
multi-source user data upload, dual-corpus RAG, chat agent, and RAGAS evaluation.
"""

import json, os, re, time, threading, uuid
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
    ENHANCED_GUIDE_SYSTEM_PROMPT,
    ENHANCED_GUIDE_USER_TEMPLATE,
    DATA_PROFILE_SYSTEM_PROMPT,
    DATA_PROFILE_USER_TEMPLATE,
    CHAT_SYSTEM_PROMPT,
    CHAT_USER_TEMPLATE,
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
    user_id: Optional[str] = None


class UserDataUpload(BaseModel):
    source: str  # "spotify" | "youtube" | "google_maps" | "instagram"
    data: dict
    user_id: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    city: str
    profile: str
    user_id: Optional[str] = None
    history: list[dict] = []  # [{"role": "user"|"assistant", "content": "..."}]


# In-memory user data store
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
        cities.append({
            "slug": slug,
            "name": name,
            "chunk_count": chunk_count,
            "categories": categories,
        })
    return cities


def get_city_center(city_slug: str) -> dict:
    """Return center lat/lng for a city (for map initialization)."""
    centers = {
        "buenos-aires": {"lat": -34.6037, "lng": -58.3816, "zoom": 13},
        "barcelona": {"lat": 41.3874, "lng": 2.1686, "zoom": 13},
        "lisbon": {"lat": 38.7169, "lng": -9.1399, "zoom": 13},
    }
    return centers.get(city_slug, {"lat": 0, "lng": 0, "zoom": 12})


def get_city_venues(city_slug: str) -> list[dict]:
    """Load all venues with coordinates from a city data file."""
    fp = CITIES_DIR / f"{city_slug}.json"
    if not fp.exists():
        return []
    data = json.loads(fp.read_text())
    venues = []
    for item in data:
        # Support old format: venues array inside each chunk
        for venue in item.get("venues", []):
            venues.append({
                **venue,
                "category": item.get("category", "general"),
                "chunk_id": item.get("id", ""),
                "source_type": item.get("source_type", ""),
                "source_url": item.get("source_url", ""),
            })
        # Support new format: coordinates + venue_name at top level
        coords = item.get("coordinates")
        venue_name = item.get("venue_name")
        if coords and venue_name:
            venues.append({
                "name": venue_name,
                "lat": coords["lat"],
                "lng": coords["lng"],
                "category": item.get("category", "general"),
                "chunk_id": item.get("id", ""),
                "source_type": item.get("source_type", ""),
                "source_url": item.get("source_url", ""),
                "why": item.get("text", "")[:200],
            })
    return venues


def parse_venue_lines(text: str) -> list[dict]:
    """Parse VENUE: lines from LLM chat responses."""
    venues = []
    for line in text.split("\n"):
        line = line.strip()
        if line.startswith("VENUE:"):
            parts = line[6:].strip().split("|")
            if len(parts) >= 5:
                try:
                    venues.append({
                        "name": parts[0].strip(),
                        "category": parts[1].strip(),
                        "lat": float(parts[2].strip()),
                        "lng": float(parts[3].strip()),
                        "why": parts[4].strip(),
                    })
                except (ValueError, IndexError):
                    pass
    return venues


def embed_text(text: str) -> list[float]:
    resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return resp.data[0].embedding


def embed_batch(texts: list[str]) -> list[list[float]]:
    resp = openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def chunk_text(text: str, max_words: int = 400, overlap: int = 50) -> list[str]:
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
        # Support old format (venues array) and new format (coordinates + venue_name)
        venues = item.get("venues", [])
        coords = item.get("coordinates")
        venue_name = item.get("venue_name")
        if coords and venue_name and not venues:
            venues = [{"name": venue_name, "lat": coords["lat"], "lng": coords["lng"], "neighborhood": ""}]
        venues_text = ""
        if venues:
            venues_text = "\nVenues: " + ", ".join(
                f"{v['name']} ({v.get('neighborhood', '')}, {v.get('lat', 0):.4f}/{v.get('lng', 0):.4f})"
                for v in venues
            )

        if len(text.split()) <= 500:
            embed_text_str = (
                f"City: {item.get('city', '')}\n"
                f"Category: {item.get('category', '')}\n"
                f"Source: {item.get('source_type', '')} — {item.get('source_url', '')}\n\n"
                f"{text}{venues_text}"
            )
            chunks.append({
                "id": item.get("id", f"{city_slug}-{len(chunks)}"),
                "text": embed_text_str,
                "metadata": {
                    "city": item.get("city", city_slug),
                    "category": item.get("category", "general"),
                    "source_url": item.get("source_url", ""),
                    "source_type": item.get("source_type", ""),
                    "date": item.get("date", ""),
                    "text": text[:3500],
                    "venues_json": json.dumps(venues) if venues else "",
                },
            })
        else:
            for ci, c in enumerate(chunk_text(text)):
                chunks.append({
                    "id": f"{item.get('id', city_slug)}-{ci}",
                    "text": (
                        f"City: {item.get('city', '')}\n"
                        f"Category: {item.get('category', '')}\n"
                        f"Source: {item.get('source_type', '')} — {item.get('source_url', '')}\n\n"
                        f"{c}{venues_text if ci == 0 else ''}"
                    ),
                    "metadata": {
                        "city": item.get("city", city_slug),
                        "category": item.get("category", "general"),
                        "source_url": item.get("source_url", ""),
                        "source_type": item.get("source_type", ""),
                        "date": item.get("date", ""),
                        "text": c[:3500],
                        "venues_json": json.dumps(venues) if venues and ci == 0 else "",
                    },
                })
    return chunks


# ── Dual-corpus retrieval helper ──


def retrieve_context(profile: str, city: str, top_k: int = 8, user_id: str | None = None):
    """
    Retrieve relevant context from city corpus and optionally user corpus.
    Returns: (city_sources, user_signals, all_venues)
    """
    city_slug = city.lower().replace(" ", "-")
    query_text = f"Travel recommendations for someone with this taste profile: {profile}. City: {city}"
    query_vec = embed_text(query_text)

    idx = pc.Index(INDEX)

    # City corpus query
    results = idx.query(
        vector=query_vec,
        top_k=top_k,
        include_metadata=True,
        filter={"city": {"$eq": city_slug}},
    )
    all_matches = {m.id: m for m in results.matches}

    # Category diversity queries
    for cat in ["coffee", "food", "nightlife", "culture"]:
        cat_query = f"{profile}. Best {cat} recommendations in {city}"
        cat_vec = embed_text(cat_query)
        try:
            cat_results = idx.query(
                vector=cat_vec,
                top_k=3,
                include_metadata=True,
                filter={"city": {"$eq": city_slug}},
            )
            for m in cat_results.matches:
                if m.id not in all_matches:
                    all_matches[m.id] = m
        except Exception:
            pass

    final_matches = sorted(all_matches.values(), key=lambda m: m.score, reverse=True)

    # Build sources list + extract venue coordinates
    sources = []
    all_venues = []
    for m in final_matches:
        venues_json = m.metadata.get("venues_json", "")
        venues = json.loads(venues_json) if venues_json else []
        category = m.metadata.get("category", "")
        for v in venues:
            v["category"] = category
            v["source_url"] = m.metadata.get("source_url", "")
            v["source_type"] = m.metadata.get("source_type", "")
            all_venues.append(v)

        sources.append({
            "score": m.score,
            "text": m.metadata.get("text", ""),
            "category": category,
            "source_url": m.metadata.get("source_url", ""),
            "source_type": m.metadata.get("source_type", ""),
            "city": m.metadata.get("city", ""),
            "date": m.metadata.get("date", ""),
            "venues": venues,
        })

    # User corpus query (if available)
    user_signals = []
    has_user_data = user_id and user_id in user_data_store
    if has_user_data:
        user_namespace = f"user_{user_id}"
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
        except Exception as e:
            print(f"  → User namespace query failed: {e}")

    return sources, user_signals, all_venues


# ── RAGAS Evaluation ──

_ragas_cache = {}


def get_ragas_evaluator():
    if not _ragas_cache:
        from ragas.llms import llm_factory
        from ragas.embeddings import embedding_factory
        _ragas_cache["llm"] = llm_factory("gpt-4o-mini")
        _ragas_cache["emb"] = embedding_factory("text-embedding-3-small")
    return _ragas_cache["llm"], _ragas_cache["emb"]


def score_with_ragas(question: str, answer: str, contexts: list[str]) -> dict:
    from ragas import SingleTurnSample, EvaluationDataset, evaluate
    from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference, ResponseRelevancy

    evaluator_llm, evaluator_emb = get_ragas_evaluator()
    sample = SingleTurnSample(user_input=question, response=answer, retrieved_contexts=contexts)
    result = evaluate(
        dataset=EvaluationDataset(samples=[sample]),
        metrics=[Faithfulness(), LLMContextPrecisionWithoutReference(), ResponseRelevancy()],
        llm=evaluator_llm,
        embeddings=evaluator_emb,
    )
    df = result.to_pandas()
    precision_col = next((c for c in df.columns if "precision" in c.lower()), None)
    relevancy_col = next((c for c in df.columns if "relevancy" in c.lower()), None)
    return {
        "faithfulness": round(float(df["faithfulness"].iloc[0]), 3),
        "context_precision": round(float(df[precision_col].iloc[0]), 3) if precision_col else None,
        "relevancy": round(float(df[relevancy_col].iloc[0]), 3) if relevancy_col else None,
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
                name=INDEX, dimension=1536, metric="cosine",
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


# ═══════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "cityscout-rag"}


@app.get("/api/cities")
def list_cities():
    cities = get_available_cities()
    # Add center coordinates for each city
    for city in cities:
        center = get_city_center(city["slug"])
        city["center"] = center
    return {"cities": cities}


@app.post("/api/ingest")
def ingest():
    if ingest_state["running"]:
        raise HTTPException(409, "Ingestion already running")
    ingest_state.update(running=True, phase="loading", total=0, processed=0, error=None)
    threading.Thread(target=run_ingestion, daemon=True).start()
    return {"message": "Ingestion started", "state": ingest_state}


@app.get("/api/ingest/status")
def ingestion_status():
    return ingest_state


# ── Profile from quiz (legacy, kept for compatibility) ──


@app.post("/api/profile")
def generate_profile(req: ProfileRequest):
    t_start = time.time()
    answers = req.quiz_answers
    user_prompt = PROFILE_USER_TEMPLATE.format(
        coffee=answers.coffee, food=answers.food, activity=answers.activity,
        nightlife=answers.nightlife, neighborhood=answers.neighborhood, budget=answers.budget,
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
    return {
        "profile": profile,
        "usage": {
            "prompt_tokens": completion.usage.prompt_tokens,
            "completion_tokens": completion.usage.completion_tokens,
            "total_tokens": completion.usage.total_tokens,
        },
    }


# ── User Data Upload ──


@app.post("/api/profile/upload")
def upload_user_data(req: UserDataUpload):
    t_start = time.time()
    if req.source not in PARSERS:
        raise HTTPException(400, f"Unknown source: {req.source}. Valid: {list(PARSERS.keys())}")

    user_id = req.user_id or str(uuid.uuid4())[:8]
    namespace = f"user_{user_id}"

    print(f"\n[upload] Processing {req.source} for user {user_id}")

    try:
        signal_chunks = parse_user_data(req.source, req.data)
    except Exception as e:
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

    # Embed and store
    texts = [c["text"] for c in signal_chunks]
    embeddings = embed_batch(texts)

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

    # Track user data
    if user_id not in user_data_store:
        user_data_store[user_id] = {"sources": [], "chunk_count": 0, "signals": []}
    user_data_store[user_id]["sources"].append(req.source)
    user_data_store[user_id]["chunk_count"] += len(vectors)
    user_data_store[user_id]["signals"].extend(signal_chunks)

    elapsed = time.time() - t_start
    print(f"  → Done in {elapsed:.2f}s, {len(vectors)} vectors stored")

    return {
        "user_id": user_id,
        "source": req.source,
        "chunks_stored": len(vectors),
        "signal_types": list(set(c["metadata"]["signal_type"] for c in signal_chunks)),
        "categories": list(set(c["metadata"]["category"] for c in signal_chunks)),
        "signals": [
            {"type": c["metadata"]["signal_type"], "category": c["metadata"]["category"],
             "preview": c["text"][:120]}
            for c in signal_chunks
        ],
    }


@app.get("/api/profile/user/{user_id}")
def get_user_data_status(user_id: str):
    info = user_data_store.get(user_id)
    if not info:
        raise HTTPException(404, f"No data found for user {user_id}")
    return {
        "user_id": user_id,
        "sources": list(set(info["sources"])),
        "chunk_count": info["chunk_count"],
        "namespace": f"user_{user_id}",
    }


# ── Profile from uploaded data (NEW — no quiz needed) ──


@app.post("/api/profile/generate")
def generate_profile_from_data(req: dict):
    """
    Generate a taste profile purely from uploaded user data signals.
    No quiz needed — the connected data IS the profile.
    """
    user_id = req.get("user_id")
    if not user_id or user_id not in user_data_store:
        raise HTTPException(400, "No user data uploaded. Upload data first.")

    t_start = time.time()
    print(f"\n[profile/generate] Generating profile from data for user {user_id}")

    # Retrieve all user signal chunks
    user_info = user_data_store[user_id]
    signal_texts = [c["text"] for c in user_info["signals"]]
    sources_used = list(set(user_info["sources"]))

    if not signal_texts:
        raise HTTPException(400, "No signals found in uploaded data")

    user_prompt = DATA_PROFILE_USER_TEMPLATE.format(
        sources=", ".join(sources_used),
        signal_count=len(signal_texts),
        signals="\n".join(f"- {s[:200]}" for s in signal_texts),
    )

    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": DATA_PROFILE_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.8,
        max_tokens=400,
    )

    profile = completion.choices[0].message.content.strip()
    elapsed = time.time() - t_start
    print(f"  → Profile: {profile[:100]}...")
    print(f"  → Generated in {elapsed:.2f}s")

    return {
        "profile": profile,
        "user_id": user_id,
        "data_sources": sources_used,
        "signal_count": len(signal_texts),
        "usage": {
            "prompt_tokens": completion.usage.prompt_tokens,
            "completion_tokens": completion.usage.completion_tokens,
            "total_tokens": completion.usage.total_tokens,
        },
    }


# ── Guide Generation (dual-corpus RAG) ──


@app.post("/api/guide")
def generate_guide(req: GuideRequest):
    t_start = time.time()
    has_user_data = req.user_id and req.user_id in user_data_store
    city_slug = req.city.lower().replace(" ", "-")
    city_name = req.city.replace("-", " ").title()
    print(f"\n{'='*70}")
    print(f"[guide] Generating {'enhanced ' if has_user_data else ''}guide for {city_name}")

    # Retrieve context
    sources, user_signals, all_venues = retrieve_context(
        req.profile, req.city, req.top_k, req.user_id
    )

    print(f"  → {len(sources)} city sources, {len(user_signals)} user signals, {len(all_venues)} venue pins")

    # Build context string
    context = "\n\n---\n\n".join(
        f"[{i+1}] Category: {s['category']} | Source: {s['source_type']} — {s['source_url']}\n{s['text']}"
        for i, s in enumerate(sources)
    )

    # Choose prompt
    if has_user_data and user_signals:
        user_context = "\n\n".join(
            f"[{s['source_type'].upper()}] ({s['category']}/{s['signal_type']}): {s['text']}"
            for s in user_signals
        )
        user_prompt = ENHANCED_GUIDE_USER_TEMPLATE.format(
            profile=req.profile, city=city_name, context=context, user_context=user_context,
        )
        system_prompt = ENHANCED_GUIDE_SYSTEM_PROMPT
    else:
        user_prompt = GUIDE_USER_TEMPLATE.format(
            profile=req.profile, city=city_name, context=context,
        )
        system_prompt = GUIDE_SYSTEM_PROMPT

    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=3000,
    )

    guide = completion.choices[0].message.content
    tokens = completion.usage

    # RAGAS evaluation
    contexts_for_eval = [s["text"] for s in sources]
    if user_signals:
        contexts_for_eval.extend([s["text"] for s in user_signals])

    try:
        scores = score_with_ragas(
            f"Personalized {city_name} guide for: {req.profile[:200]}",
            guide, contexts_for_eval,
        )
    except Exception as e:
        print(f"  → RAGAS failed: {e}")
        scores = {"error": str(e), "faithfulness": None, "context_precision": None, "relevancy": None}

    # City center for map
    center = get_city_center(city_slug)

    elapsed = time.time() - t_start
    print(f"  → Generated in {elapsed:.2f}s")

    return {
        "guide": guide,
        "sources": sources,
        "user_signals": user_signals if user_signals else None,
        "scores": scores,
        "city": req.city,
        "enhanced": bool(has_user_data and user_signals),
        "venues": all_venues,
        "map_center": center,
        "usage": {
            "prompt_tokens": tokens.prompt_tokens,
            "completion_tokens": tokens.completion_tokens,
            "total_tokens": tokens.total_tokens,
        },
    }


# ── Chat Agent (conversational RAG) ──


@app.post("/api/chat")
def chat(req: ChatRequest):
    """
    Conversational RAG agent. Each message triggers a retrieval step
    and the LLM has the full conversation history for context.
    """
    t_start = time.time()
    city_slug = req.city.lower().replace(" ", "-")
    city_name = req.city.replace("-", " ").title()
    has_user_data = req.user_id and req.user_id in user_data_store

    print(f"\n[chat] User: {req.message[:80]}...")
    print(f"[chat] City: {city_name} | user_id: {req.user_id or 'none'} | history: {len(req.history)} msgs")

    # Step 1: Embed user message for retrieval
    search_query = f"{req.message}. City: {city_name}. User profile: {req.profile[:200]}"
    query_vec = embed_text(search_query)

    # Step 2: Retrieve relevant city knowledge
    idx = pc.Index(INDEX)
    try:
        results = idx.query(
            vector=query_vec,
            top_k=6,
            include_metadata=True,
            filter={"city": {"$eq": city_slug}},
        )
        city_chunks = results.matches
    except Exception as e:
        print(f"  → City search failed: {e}")
        city_chunks = []

    # Step 3: Retrieve user signals (if available)
    user_signal_texts = []
    if has_user_data:
        try:
            user_results = idx.query(
                vector=query_vec,
                top_k=5,
                include_metadata=True,
                namespace=f"user_{req.user_id}",
            )
            user_signal_texts = [m.metadata.get("text", "") for m in user_results.matches]
        except Exception:
            pass

    # Build context from retrieved chunks
    context_parts = []
    venues_in_response = []
    for m in city_chunks:
        text = m.metadata.get("text", "")
        category = m.metadata.get("category", "")
        source_url = m.metadata.get("source_url", "")
        source_type = m.metadata.get("source_type", "")
        context_parts.append(
            f"[{category}] (Source: {source_type} — {source_url})\n{text}"
        )
        # Extract venues
        venues_json = m.metadata.get("venues_json", "")
        if venues_json:
            try:
                venues = json.loads(venues_json)
                for v in venues:
                    v["category"] = category
                    v["source_url"] = source_url
                    venues_in_response.append(v)
            except json.JSONDecodeError:
                pass

    context = "\n\n---\n\n".join(context_parts) if context_parts else "No relevant local knowledge found."

    user_signals_text = ""
    if user_signal_texts:
        user_signals_text = "\n\nUser's personal data signals:\n" + "\n".join(f"- {s}" for s in user_signal_texts)

    # Step 4: Build messages list
    system_prompt = CHAT_SYSTEM_PROMPT.format(city=city_name, profile=req.profile)

    messages = [{"role": "system", "content": system_prompt}]

    # Add conversation history
    for msg in req.history[-10:]:  # Last 10 messages for context window management
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Current user message with retrieval context
    current_msg = CHAT_USER_TEMPLATE.format(
        message=req.message,
        context=context,
        user_signals=user_signals_text,
    )
    messages.append({"role": "user", "content": current_msg})

    # Step 5: Generate response
    completion = openai_client.chat.completions.create(
        model=CHAT_MODEL,
        messages=messages,
        temperature=0.5,
        max_tokens=1500,
    )

    raw_response = completion.choices[0].message.content.strip()
    tokens = completion.usage
    elapsed = time.time() - t_start

    # Parse VENUE lines from LLM response
    parsed_venues = parse_venue_lines(raw_response)

    # Clean VENUE lines from the displayed message
    clean_lines = [
        line for line in raw_response.split("\n")
        if not line.strip().startswith("VENUE:")
    ]
    clean_response = "\n".join(clean_lines).strip()

    # Combine parsed venues with context-based venues
    all_venues = venues_in_response + parsed_venues

    print(f"  → Response: {clean_response[:80]}...")
    print(f"  → {elapsed:.2f}s | {tokens.total_tokens} tokens | {len(city_chunks)} sources | {len(all_venues)} venues")

    return {
        "message": clean_response,
        "recommendations": [
            {
                "name": v.get("name", ""),
                "lat": v.get("lat", 0),
                "lng": v.get("lng", 0),
                "category": v.get("category", "general"),
                "why": v.get("why", ""),
            }
            for v in all_venues
        ],
        "sources_used": len(city_chunks),
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
