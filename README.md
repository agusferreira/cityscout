# 🧭 CityScout — Personalized City Guides Powered by RAG

CityScout creates hyper-personalized travel guides by combining a taste quiz with Retrieval-Augmented Generation (RAG). It ingests local knowledge (Reddit posts, blog articles, curated tips) into Pinecone, then generates narrative city guides tailored to each user's preferences — with source citations for every recommendation.

## Architecture

```
┌────────────────────────────────────────────────┐
│  Next.js 16 Frontend (Tailwind 4, Dark Theme)  │
│  Quiz → Profile → City Select → Guide Display  │
└───────────────┬────────────────────────────────┘
                │ REST API
┌───────────────▼────────────────────────────────┐
│  FastAPI Backend                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Profile  │  │  RAG     │  │   RAGAS      │  │
│  │ Generator│  │ Pipeline │  │  Evaluation  │  │
│  └──────────┘  └────┬─────┘  └──────────────┘  │
│                     │                           │
│  ┌──────────────────▼──────────────────────┐   │
│  │  Pinecone Vector DB (cosine, 1536 dim)  │   │
│  │  Metadata filters: city, category       │   │
│  └─────────────────────────────────────────┘   │
│                     │                           │
│  ┌──────────────────▼──────────────────────┐   │
│  │  OpenAI / OpenRouter                    │   │
│  │  Embeddings: text-embedding-3-small     │   │
│  │  Generation: gpt-4o-mini                │   │
│  └─────────────────────────────────────────┘   │
└─────────────────────────────────────────────────┘
```

## Product Flow

1. **Taste Quiz** — 6 visual preference questions (coffee, food, activities, nightlife, neighborhood, budget)
2. **Profile Generation** — LLM synthesizes a "Travel DNA" profile from answers
3. **City Selection** — User picks from available cities (Buenos Aires, Barcelona, Lisbon)
4. **RAG Pipeline** — Profile-aware multi-query against Pinecone with metadata filtering
5. **Personalized Guide** — Narrative guide with citations, category sections, and "why this matches you" explanations
6. **RAGAS Evaluation** — Faithfulness, Context Precision, and Relevancy scores on every query

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | Next.js 16, React 19, Tailwind CSS 4 |
| Backend | FastAPI (Python) |
| Vector DB | Pinecone (Serverless, cosine, 1536 dims) |
| Embeddings | OpenAI `text-embedding-3-small` |
| Generation | OpenAI `gpt-4o-mini` |
| Evaluation | RAGAS (Faithfulness, ContextPrecision, ResponseRelevancy) |
| Data | Curated JSON files (Reddit posts, blogs, local tips) |

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- OpenAI API key (or OpenRouter for proxy)
- Pinecone API key

### Backend

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Run tests
cd api && python -m pytest tests/ -v

# Start API server
python api/server.py
```

### Frontend

```bash
cd web
npm install
npm run dev
```

### Data Ingestion

1. Start the API server
2. Click "Index Data" on the landing page, or:
```bash
curl -X POST http://localhost:3001/api/ingest
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/cities` | List available cities |
| POST | `/api/ingest` | Start data ingestion |
| GET | `/api/ingest/status` | Ingestion progress |
| POST | `/api/profile` | Generate taste profile from quiz |
| POST | `/api/guide` | Generate personalized guide (main RAG pipeline) |

## RAG Pipeline Details

The guide generation endpoint runs a multi-step RAG pipeline:

1. **Embed** — User profile is embedded as the query vector
2. **Retrieve** — Multi-query Pinecone search with city metadata filter + category-specific diversity queries
3. **Generate** — LLM synthesizes a narrative guide with source citations
4. **Evaluate** — RAGAS scores the response for faithfulness, precision, and relevancy

All steps are extensively logged to demonstrate the pipeline behavior.

## Data Format

City data files (`data/cities/*.json`) contain arrays of knowledge chunks:

```json
{
  "id": "ba-coffee-01",
  "city": "buenos-aires",
  "category": "coffee",
  "source_type": "reddit",
  "source_url": "https://reddit.com/r/BuenosAires/comments/...",
  "date": "2024-11-15",
  "text": "Best specialty coffee in Buenos Aires — hands down LAB Tostadores..."
}
```

Categories: `coffee`, `food`, `nightlife`, `culture`, `neighborhoods`, `fitness`
Source types: `reddit`, `blog`, `local_tip`

## Testing

```bash
cd api
python -m pytest tests/test_rag.py -v
```

Tests cover:
- Text chunking strategy
- City data loading and validation
- Profile generation (mocked)
- Guide generation with citations (mocked)
- RAGAS evaluation structure
- API endpoint availability
- Data quality validation

## License

MIT
