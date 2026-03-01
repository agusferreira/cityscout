# Newsletter RAG – Semantic Search & Analysis

A RAG (Retrieval-Augmented Generation) system that indexes your email newsletters and lets you ask questions about them using semantic search and OpenAI.

## Architecture

```
rag-newsletter/
├── api/server.py       FastAPI — mbox parsing, embedding, Pinecone ingestion, RAG queries
├── web/                Next.js frontend — chat UI with test suite
├── data/               Cached parsed chunks (auto-generated)
├── Emails/Correo/      Source mbox file
├── requirements.txt    Python dependencies
└── .env                API keys
```

### Stack

| Layer       | Tech                            |
| ----------- | ------------------------------- |
| Frontend    | Next.js 16, Tailwind CSS 4      |
| API         | Python / FastAPI                 |
| Embeddings  | OpenAI `text-embedding-3-small` |
| Vector DB   | Pinecone (serverless)           |
| LLM         | OpenAI `gpt-4o-mini`            |

## Setup

### 1. Environment Variables

Edit `rag-newsletter/.env`:

```env
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX=newsletter-rag
API_PORT=3001
```

The OpenAI key is loaded from the parent `deep_atlas_mli/.env` automatically. You can also set `OPENAI_API_KEY` in this `.env` to override.

### 2. Get a Pinecone API Key

1. Sign up at [pinecone.io](https://www.pinecone.io/)
2. Create a free serverless project
3. Copy the API key into `.env`

### 3. Install Dependencies

```bash
# API (Python)
cd rag-newsletter
pip install -r requirements.txt

# Frontend (Node)
cd web
npm install
```

### 4. Start the API

```bash
cd rag-newsletter
python api/server.py
```

The API runs on `http://localhost:3001`.

### 5. Start the Frontend

```bash
cd rag-newsletter/web
npm run dev
```

The frontend runs on `http://localhost:3000`.

## Usage

### Step 1: Ingest Newsletters

Click **"Run Ingestion"** in the sidebar. This will:

1. **Parse** the mbox file using Python's `mailbox` module — extract emails, decode MIME, strip HTML
2. **Chunk** each email into ~500-word overlapping segments
3. **Embed** each chunk using OpenAI `text-embedding-3-small`
4. **Upsert** vectors into Pinecone

Progress is shown in real-time. Ingestion runs in a background thread.

### Step 2: Ask Questions

Type any question or click a pre-built test question from the sidebar. The system will:

1. Embed your question
2. Find the top-5 most semantically similar newsletter chunks in Pinecone
3. Feed those chunks as context to GPT-4o-mini
4. Return a synthesized answer with source references

## API Endpoints

| Method | Endpoint             | Description                                |
| ------ | -------------------- | ------------------------------------------ |
| POST   | `/api/ingest`        | Start mbox parsing + embedding pipeline    |
| GET    | `/api/ingest/status` | Check ingestion progress                   |
| POST   | `/api/query`         | RAG query `{ question, top_k? }`           |
| GET    | `/api/health`        | Health check                               |

## Test Suite

The frontend includes pre-built test questions organized by category:

- **Overview** — corpus-level summaries and topic analysis
- **Insights** — actionable advice, trends, and patterns
- **Metadata** — senders, date ranges, frequently mentioned entities
