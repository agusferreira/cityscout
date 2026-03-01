import json, os, re, time, threading, mailbox
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from pathlib import Path

import html2text
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR.parent / ".env")

MBOX_PATH = BASE_DIR / "Emails" / "Correo" / "Todo el correo, incluido Spam y Papelera.mbox"
CHUNKS_PATH = BASE_DIR / "data" / "chunks.json"
INDEX = os.getenv("PINECONE_INDEX", "newsletter-rag")

openai_client = OpenAI()
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))

# html2text: converts HTML emails to clean plain text in one call
h2t = html2text.HTML2Text()
h2t.ignore_links = True
h2t.ignore_images = True
h2t.ignore_emphasis = True

app = FastAPI(title="Newsletter RAG")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

ingest_state = {"running": False, "phase": "idle", "total": 0, "processed": 0, "error": None}


# ── Helpers ──

def header(msg, key):
    """Decode RFC2047 email header to plain string."""
    raw = msg[key]
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:
        return str(raw)


def get_body(msg):
    """Extract readable text from an email, handling multipart and HTML."""
    texts, htmls = [], []
    for part in msg.walk():
        if part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        decoded = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
        ct = part.get_content_type()
        if ct == "text/plain":
            texts.append(decoded)
        elif ct == "text/html":
            htmls.append(decoded)

    raw = "\n".join(texts) if texts else h2t.handle("\n".join(htmls)) if htmls else ""
    return re.sub(r"\s+", " ", raw).strip()


def chunk(text, size=500, overlap=75):
    """Split text into overlapping word-level chunks."""
    words = text.split()
    if len(words) <= size:
        return [text] if words else []
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i : i + size]))
        i += size - overlap
    return chunks


# ── Ingestion (runs in background thread) ──

def run_ingestion():
    global ingest_state
    try:
        ingest_state["phase"] = "parsing"
        mbox = mailbox.mbox(str(MBOX_PATH))
        all_chunks, cid = [], 0

        for i, msg in enumerate(mbox):
            body = get_body(msg)
            if len(body) < 50:
                continue

            date = ""
            try:
                date = parsedate_to_datetime(msg["date"]).isoformat()
            except Exception:
                date = msg["date"] or ""

            meta = {
                "subject": header(msg, "subject") or "No Subject",
                "from": header(msg, "from") or "Unknown",
                "date": date,
            }
            for c in chunk(body):
                # Prepend metadata so the embedding captures subject/sender context
                embed_text = f"Subject: {meta['subject']}\nFrom: {meta['from']}\nDate: {meta['date']}\n\n{c}"
                all_chunks.append({"id": f"c-{cid}", "text": embed_text, "meta": meta})
                cid += 1

            if (i + 1) % 100 == 0:
                print(f"[parse] {i + 1} emails → {len(all_chunks)} chunks")

        print(f"[parse] ✓ {len(all_chunks)} chunks")
        ingest_state["total"] = len(all_chunks)
        CHUNKS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CHUNKS_PATH.write_text(json.dumps(all_chunks))

        # Ensure Pinecone index
        ingest_state["phase"] = "embedding"
        if INDEX not in [idx.name for idx in pc.list_indexes()]:
            print(f"[ingest] Creating index '{INDEX}'...")
            pc.create_index(
                name=INDEX, dimension=1536, metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1"),
            )
            time.sleep(30)

        idx = pc.Index(INDEX)

        # Embed + upsert in batches of 50
        for i in range(0, len(all_chunks), 50):
            batch = all_chunks[i : i + 50]
            embs = openai_client.embeddings.create(
                model="text-embedding-3-small", input=[c["text"] for c in batch]
            ).data

            idx.upsert(vectors=[
                {
                    "id": c["id"],
                    "values": e.embedding,
                    "metadata": {"text": c["text"][:3500], **c["meta"]},
                }
                for c, e in zip(batch, embs)
            ])

            ingest_state["processed"] = min(i + 50, len(all_chunks))
            print(f"[ingest] {ingest_state['processed']}/{len(all_chunks)}")
            time.sleep(0.3)

        ingest_state.update(phase="done", running=False)
        print("[ingest] ✓ Done")

    except Exception as e:
        print(f"[ingest] Error: {e}")
        ingest_state.update(phase="error", error=str(e), running=False)


# ── Routes ──

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/ingest")
def ingest():
    if ingest_state["running"]:
        raise HTTPException(409, "Already running")
    ingest_state.update(running=True, phase="parsing", total=0, processed=0, error=None)
    threading.Thread(target=run_ingestion, daemon=True).start()
    return {"message": "Started", "state": ingest_state}


@app.get("/api/ingest/status")
def status():
    return ingest_state


class Query(BaseModel):
    question: str
    top_k: int = 5


SYSTEM_PROMPT = (
    "You are an Email Analysis Expert. Answer using ONLY the provided context. "
    "Mention source subject/sender when relevant. Use markdown. "
    "If context is insufficient, say so."
)


# Lazy-init RAGAS evaluator (reused across requests)
_ragas_cache = {}

def get_ragas_evaluator():
    """Use ragas native factories instead of deprecated langchain wrappers."""
    if not _ragas_cache:
        from ragas.llms import llm_factory
        from ragas.embeddings import embedding_factory
        _ragas_cache["llm"] = llm_factory("gpt-4o-mini")
        _ragas_cache["emb"] = embedding_factory("text-embedding-3-small")
        print("[ragas] Evaluator initialized (gpt-4o-mini + text-embedding-3-small)")
    return _ragas_cache["llm"], _ragas_cache["emb"]


def score_with_ragas(question: str, answer: str, contexts: list[str]) -> dict:
    """
    Evaluate a single RAG result using RAGAS metrics:
    - Faithfulness: is the answer grounded in the retrieved contexts? (detects hallucination)
    - ContextPrecision: are the retrieved chunks relevant and well-ranked?
    - ResponseRelevancy: does the answer actually address the question asked?
    """
    from ragas import SingleTurnSample, EvaluationDataset, evaluate
    from ragas.metrics.collections import Faithfulness, LLMContextPrecisionWithoutReference, ResponseRelevancy

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
        "context_precision": round(float(df[precision_col].iloc[0]), 3) if precision_col else None,
        "relevancy": round(float(df[relevancy_col].iloc[0]), 3) if relevancy_col else None,
    }


def _score_label(val):
    """Human-readable quality label for a RAGAS score."""
    if val is None:
        return "N/A"
    if val >= 0.8:
        return f"{val:.3f} ✓ GOOD"
    if val >= 0.5:
        return f"{val:.3f} ~ OK"
    return f"{val:.3f} ✗ LOW"


@app.post("/api/query")
def query(req: Query):
    t_start = time.time()
    print(f"\n{'='*70}")
    print(f"[query] Question: \"{req.question}\"")
    print(f"[query] Config: top_k={req.top_k}, index={INDEX}")
    print(f"{'─'*70}")

    # ── Step 1: Retrieve ──
    print("[1/3 RETRIEVE] Embedding question...")
    t1 = time.time()
    qvec = openai_client.embeddings.create(
        model="text-embedding-3-small", input=req.question
    ).data[0].embedding
    t_embed = time.time() - t1
    print(f"  → Embedding: {t_embed:.2f}s | dim={len(qvec)} | model=text-embedding-3-small")

    print(f"  → Querying Pinecone index '{INDEX}'...")
    t2 = time.time()
    matches = pc.Index(INDEX).query(
        vector=qvec, top_k=req.top_k, include_metadata=True
    ).matches
    t_search = time.time() - t2
    print(f"  → Search: {t_search:.2f}s | {len(matches)} chunks retrieved")

    sources = [
        {
            "score": m.score,
            "text": m.metadata.get("text", ""),
            "subject": m.metadata.get("subject", ""),
            "from": m.metadata.get("from", ""),
            "date": m.metadata.get("date", ""),
        }
        for m in matches
    ]

    print(f"  {'─'*66}")
    total_ctx_chars = 0
    for i, s in enumerate(sources):
        chars = len(s["text"])
        total_ctx_chars += chars
        preview = s["text"][:80].replace("\n", " ")
        print(f"  [{i+1}] score={s['score']:.4f} | {chars:,} chars")
        print(f"      from: {s['from'][:50]}")
        print(f"      subj: {s['subject'][:60]}")
        print(f"      date: {s['date']}")
        print(f"      text: \"{preview}...\"")
    print(f"  {'─'*66}")
    print(f"  Total context: {total_ctx_chars:,} chars across {len(sources)} chunks")

    # ── Step 2: Generate ──
    print(f"{'─'*70}")
    print("[2/3 GENERATE] Sending to LLM...")
    ctx = "\n\n---\n\n".join(
        f"[{i + 1}] {s['from']} | {s['subject']} | {s['date']}\n{s['text']}"
        for i, s in enumerate(sources)
    )
    prompt_text = f"Context:\n\n{ctx}\n\n---\nQuestion: {req.question}"
    print(f"  → System prompt: {len(SYSTEM_PROMPT)} chars")
    print(f"  → User prompt: {len(prompt_text):,} chars (context + question)")

    t3 = time.time()
    completion = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ],
        temperature=0.3,
        max_tokens=1200,
    )
    t_gen = time.time() - t3

    answer = completion.choices[0].message.content
    contexts = [s["text"] for s in sources]
    tokens = completion.usage
    print(f"  → LLM responded in {t_gen:.2f}s | model=gpt-4o-mini | temp=0.3")
    print(f"  → Tokens: prompt={tokens.prompt_tokens:,} + completion={tokens.completion_tokens:,} = {tokens.total_tokens:,}")
    print(f"  → Answer length: {len(answer):,} chars")
    for line in answer.split("\n")[:5]:
        print(f"  │ {line[:90]}")
    if answer.count("\n") > 5:
        print(f"  │ ... ({answer.count(chr(10)) - 5} more lines)")

    # ── Step 3: Evaluate with RAGAS ──
    print(f"{'─'*70}")
    print("[3/3 RAGAS] Evaluating retrieval + generation quality...")
    print(f"  → Metrics: Faithfulness, ContextPrecision, ResponseRelevancy")
    print(f"  → Input: question ({len(req.question)} chars) + answer ({len(answer)} chars) + {len(contexts)} contexts ({total_ctx_chars:,} chars)")
    t4 = time.time()
    try:
        scores = score_with_ragas(req.question, answer, contexts)
        t_ragas = time.time() - t4
        print(f"  → Completed in {t_ragas:.2f}s")
        print(f"  ┌────────────────────────────────────────────┐")
        print(f"  │  Faithfulness:      {_score_label(scores['faithfulness']):>20} │")
        print(f"  │  Context Precision: {_score_label(scores['context_precision']):>20} │")
        print(f"  │  Relevancy:         {_score_label(scores['relevancy']):>20} │")
        print(f"  └────────────────────────────────────────────┘")
    except Exception as e:
        t_ragas = time.time() - t4
        print(f"  → FAILED in {t_ragas:.2f}s: {e}")
        scores = {"error": str(e)}

    # ── Summary ──
    total = time.time() - t_start
    print(f"{'─'*70}")
    print(f"[summary] embed={t_embed:.2f}s → search={t_search:.2f}s → generate={t_gen:.2f}s → ragas={t_ragas:.2f}s")
    print(f"[summary] Total: {total:.2f}s | {tokens.total_tokens:,} tokens")
    print(f"{'='*70}\n")

    return {
        "answer": answer,
        "sources": sources,
        "scores": scores,
        "usage": {
            "prompt_tokens": tokens.prompt_tokens,
            "completion_tokens": tokens.completion_tokens,
            "total_tokens": tokens.total_tokens,
        },
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", "3001"))
    print(f"Email RAG API → http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
