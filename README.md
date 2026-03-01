# 🧭 CityScout — Personalized City Guides Powered by Multi-Source RAG

CityScout creates hyper-personalized travel guides by combining your digital footprint (Spotify, YouTube, Google Maps, Instagram) with local city knowledge through a **dual-corpus Retrieval-Augmented Generation (RAG)** pipeline. It synthesizes recommendations from Reddit posts, blogs, and local tips — personalized to YOUR taste — with source citations for every recommendation.

## System Architecture

```mermaid
graph TB
    subgraph Frontend["🖥️ Next.js 16 Frontend (Tailwind 4, Dark Theme)"]
        A[Connect Your Data] --> B[Destination Selection]
        B --> C[Results: Map + Chat Agent]
    end

    subgraph DataSources["📥 User Data Sources"]
        S1[🎵 Spotify<br/>Listening History]
        S2[📺 YouTube<br/>Subscriptions]
        S3[📍 Google Maps<br/>Saved Places]
        S4[📸 Instagram<br/>Likes & Saves]
        S5[📅 Google Calendar<br/>Free Time Slots]
    end

    subgraph Backend["⚙️ FastAPI Backend"]
        P[Source Parsers<br/>parsers.py]
        PG[Profile Generator<br/>LLM Synthesis]
        RAG[RAG Pipeline<br/>Dual-Corpus Retrieval]
        CE[Chat Engine<br/>Conversational RAG]
        RE[RAGAS Evaluator<br/>Quality Scoring]
    end

    subgraph Storage["💾 Vector Storage"]
        PC[(Pinecone<br/>Serverless<br/>cosine · 1536d)]
    end

    subgraph LLM["🧠 LLM Layer"]
        EMB[text-embedding-3-small<br/>Embedding Model]
        GEN[gpt-4o-mini<br/>Generation Model]
    end

    S1 & S2 & S3 & S4 & S5 --> P
    P --> PG
    PG --> RAG
    A -->|Upload JSON| P
    B -->|City + Profile| RAG
    C -->|User Message| CE
    RAG --> RE
    RAG --> C
    CE --> C
    RAG <--> PC
    CE <--> PC
    RAG <--> EMB
    RAG <--> GEN
    CE <--> GEN
    P --> EMB
    EMB --> PC

    style Frontend fill:#1a1a2e,stroke:#e94560,color:#fff
    style Backend fill:#16213e,stroke:#0f3460,color:#fff
    style Storage fill:#0f3460,stroke:#533483,color:#fff
    style LLM fill:#533483,stroke:#e94560,color:#fff
    style DataSources fill:#1a1a2e,stroke:#533483,color:#fff
```

## RAG Pipeline — Deep Dive

The core of CityScout is a **dual-corpus RAG** system that retrieves from two separate knowledge bases and synthesizes a unified, personalized response.

```mermaid
flowchart TD
    subgraph Input["1️⃣ INPUT"]
        UP[User Profile<br/>Generated from connected data]
        CT[Target City<br/>e.g. Barcelona]
    end

    subgraph QueryGen["2️⃣ QUERY GENERATION"]
        MQ[Main Query<br/>"Recommendations for someone who<br/>loves jazz, specialty coffee,<br/>casual dining in Barcelona"]
        CQ1[Category Query: Coffee<br/>"Best specialty coffee for<br/>third-wave enthusiast"]
        CQ2[Category Query: Food<br/>"Casual restaurants, Japanese,<br/>Mexican cuisine"]
        CQ3[Category Query: Nightlife<br/>"Jazz bars, cocktail bars,<br/>not clubs"]
        CQ4[Category Query: Culture<br/>"Art galleries, indie bookstores,<br/>local markets"]
    end

    subgraph Embedding["3️⃣ EMBEDDING"]
        E1[/"text-embedding-3-small<br/>1536 dimensions<br/>OpenAI API"/]
    end

    subgraph Retrieval["4️⃣ DUAL-CORPUS RETRIEVAL"]
        subgraph CityCorpus["City Knowledge Corpus"]
            CC[(Pinecone<br/>filter: city=barcelona)]
            CC1[Reddit posts from r/Barcelona]
            CC2[Travel blog articles]
            CC3[Local tips & guides]
            CC --> CC1 & CC2 & CC3
        end
        subgraph UserCorpus["User Data Corpus"]
            UC[(Pinecone<br/>namespace: user_{id})]
            UC1[Spotify: jazz, bossa nova,<br/>indie rock patterns]
            UC2[Maps: wine bars, ramen joints,<br/>CrossFit gyms frequented]
            UC3[YouTube: travel vlogs,<br/>food channels watched]
            UC4[Instagram: aesthetic preferences,<br/>lifestyle signals]
            UC --> UC1 & UC2 & UC3 & UC4
        end
    end

    subgraph Rerank["5️⃣ DEDUPLICATION & RANKING"]
        DR[Deduplicate by chunk ID<br/>Sort by cosine similarity score<br/>Ensure category diversity]
    end

    subgraph Synthesis["6️⃣ LLM SYNTHESIS"]
        SY[/"gpt-4o-mini<br/>System: Guide generation prompt<br/>Context: city chunks + user signals<br/>Output: narrative guide with citations"/]
    end

    subgraph Output["7️⃣ OUTPUT"]
        NG[📖 Narrative Guide<br/>"Your first morning in Barcelona:<br/>walk to Satan's Coffee Corner..."]
        MP[🗺️ Map Pins<br/>Lat/lng for each venue<br/>Color-coded by category]
        SC[📎 Source Citations<br/>Reddit post, blog URL,<br/>similarity score]
        RS[📊 RAGAS Scores<br/>Faithfulness, Precision,<br/>Relevancy]
    end

    UP & CT --> MQ
    UP --> CQ1 & CQ2 & CQ3 & CQ4
    MQ & CQ1 & CQ2 & CQ3 & CQ4 --> E1
    E1 -->|"5 query vectors"| CC
    E1 -->|"main query vector"| UC
    CC1 & CC2 & CC3 --> DR
    UC1 & UC2 & UC3 & UC4 --> DR
    DR -->|"top-K city chunks<br/>+ top-10 user signals"| SY
    SY --> NG & MP & SC & RS

    style Input fill:#1a1a2e,stroke:#e94560,color:#fff
    style QueryGen fill:#16213e,stroke:#0f3460,color:#fff
    style Embedding fill:#533483,stroke:#e94560,color:#fff
    style CityCorpus fill:#0f3460,stroke:#533483,color:#fff
    style UserCorpus fill:#0f3460,stroke:#e94560,color:#fff
    style Rerank fill:#16213e,stroke:#0f3460,color:#fff
    style Synthesis fill:#533483,stroke:#e94560,color:#fff
    style Output fill:#1a1a2e,stroke:#e94560,color:#fff
```

## Data Ingestion Pipeline

```mermaid
flowchart LR
    subgraph Sources["Raw Data Sources"]
        R[Reddit API<br/>City subreddits]
        B[Blog Articles<br/>Travel & food blogs]
        L[Local Tips<br/>Curated guides]
    end

    subgraph Processing["Chunk Processing"]
        CL[Clean & Normalize Text]
        CH[Chunk Strategy<br/>Reddit: 1 post = 1 chunk<br/>Blogs: ~400 words + overlap<br/>Tips: full text]
        MT[Attach Metadata<br/>city, category, source_url,<br/>source_type, date, venues]
    end

    subgraph VenueEnrich["Venue Enrichment"]
        VE[Extract Venue Names<br/>Add lat/lng coordinates<br/>Add neighborhood tags]
    end

    subgraph Indexing["Vector Indexing"]
        EM[/"Batch Embed<br/>text-embedding-3-small<br/>50 chunks per batch"/]
        UP[/"Upsert to Pinecone<br/>1536-dim vectors<br/>+ metadata payload"/]
    end

    R & B & L --> CL --> CH --> MT --> VE --> EM --> UP

    style Sources fill:#1a1a2e,stroke:#e94560,color:#fff
    style Processing fill:#16213e,stroke:#0f3460,color:#fff
    style VenueEnrich fill:#533483,stroke:#e94560,color:#fff
    style Indexing fill:#0f3460,stroke:#533483,color:#fff
```

## User Data Processing

```mermaid
flowchart TD
    subgraph Upload["User Uploads JSON Export"]
        J1["spotify-history.json<br/>{tracks: [{name, artist,<br/>genre, play_count}]}"]
        J2["youtube-subs.json<br/>{channels: [{name,<br/>category, description}]}"]
        J3["maps-saved.json<br/>{places: [{name, type,<br/>lat, lng, visits}]}"]
        J4["instagram-likes.json<br/>{posts: [{caption,<br/>hashtags, location}]}"]
    end

    subgraph Parsers["Source-Specific Parsers (parsers.py)"]
        P1["parse_spotify()<br/>→ genres, artists, mood,<br/>energy level, listening times"]
        P2["parse_youtube()<br/>→ interests, content taste,<br/>travel preferences"]
        P3["parse_google_maps()<br/>→ place types, cuisines,<br/>neighborhood vibes, price"]
        P4["parse_instagram()<br/>→ aesthetics, lifestyle,<br/>interest categories"]
    end

    subgraph Chunks["Generated Chunks"]
        C1["'Loves jazz and bossa nova.<br/>Top artists: Chet Baker,<br/>Tom Jobim. Listens mostly<br/>evenings, mellow mood.'"]
        C2["'Watches travel vlogs and<br/>food content. Interested in<br/>street food, local culture,<br/>architecture.'"]
        C3["'Frequents wine bars (12x),<br/>ramen joints (8x), specialty<br/>coffee (daily). Prefers<br/>Palermo/Recoleta areas.'"]
        C4["'Aesthetic: warm tones,<br/>cozy interiors, outdoor<br/>dining. Saves food and<br/>travel content.'"]
    end

    subgraph Store["Pinecone User Namespace"]
        NS[("namespace: user_{id}<br/>Embedded with<br/>text-embedding-3-small<br/>Tagged: source_type,<br/>category, signal_type")]
    end

    J1 --> P1 --> C1 --> NS
    J2 --> P2 --> C2 --> NS
    J3 --> P3 --> C3 --> NS
    J4 --> P4 --> C4 --> NS

    style Upload fill:#1a1a2e,stroke:#e94560,color:#fff
    style Parsers fill:#16213e,stroke:#0f3460,color:#fff
    style Chunks fill:#533483,stroke:#e94560,color:#fff
    style Store fill:#0f3460,stroke:#533483,color:#fff
```

## Chat Agent Flow

```mermaid
sequenceDiagram
    participant U as 👤 User
    participant FE as 🖥️ Frontend
    participant API as ⚙️ /api/chat
    participant PC as 💾 Pinecone
    participant LLM as 🧠 gpt-4o-mini

    U->>FE: "Any good brunch spots<br/>near the Gothic Quarter?"
    FE->>API: POST /api/chat<br/>{message, city, profile,<br/>user_id, history[]}

    Note over API: Build RAG query from<br/>message + profile context

    API->>PC: Query city corpus<br/>filter: city=barcelona<br/>query: "brunch Gothic Quarter"
    PC-->>API: Top-K city chunks<br/>(Reddit, blog matches)

    API->>PC: Query user corpus<br/>namespace: user_{id}<br/>query: "brunch preferences"
    PC-->>API: User signals<br/>(Maps: café visits,<br/>IG: brunch aesthetics)

    Note over API: Combine city chunks +<br/>user signals + chat history

    API->>LLM: Generate response<br/>System: chat prompt<br/>Context: retrieved chunks<br/>History: conversation

    LLM-->>API: "Based on your love of<br/>specialty coffee and casual<br/>vibes, check out Federal Café<br/>on Passatge de la Pau..."

    API-->>FE: {message, recommendations:<br/>[{name, lat, lng,<br/>category, why}]}
    FE->>FE: Add new pins to map
    FE-->>U: Display response +<br/>update map pins
```

## Product Flow

```mermaid
graph LR
    A["🔗 Connect Data<br/>Upload Spotify, YouTube,<br/>Maps, Instagram exports<br/>(or click 'Try Demo')"] 
    --> B["🌍 Pick Destination<br/>Choose from available<br/>cities + see your<br/>generated taste profile"]
    --> C["🗺️ Explore<br/>Interactive map with<br/>color-coded pins +<br/>conversational RAG chat"]

    style A fill:#e94560,stroke:#1a1a2e,color:#fff
    style B fill:#533483,stroke:#1a1a2e,color:#fff
    style C fill:#0f3460,stroke:#1a1a2e,color:#fff
```

## Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Frontend | Next.js 16, React 19, Tailwind CSS 4 | App shell, routing, dark theme |
| Map | Leaflet.js + react-leaflet | Interactive venue map with category pins |
| Backend | FastAPI (Python) | REST API, RAG orchestration |
| Vector DB | Pinecone (Serverless, cosine, 1536d) | Dual-corpus storage (city + user namespaces) |
| Embeddings | OpenAI `text-embedding-3-small` | 1536-dim vectors for semantic search |
| Generation | OpenAI `gpt-4o-mini` | Profile synthesis, guide narrative, chat |
| Evaluation | RAGAS | Faithfulness, Context Precision, Relevancy |
| Data | Curated JSON (Reddit, blogs, local tips) | City knowledge corpus |

## Why RAG?

CityScout demonstrates why RAG is essential for this use case:

1. **Corpus exceeds context window** — Hundreds of Reddit posts, blog articles, and local tips per city can't fit in a single LLM prompt. RAG retrieves only the most relevant chunks.

2. **Replaces hours of human research** — Users typically spend 2-5 hours reading Reddit threads, blogs, and review sites to plan a trip. RAG synthesizes this in seconds.

3. **Citations build trust** — Every recommendation links back to its source (Reddit post, blog article). Users can verify recommendations, unlike hallucination-prone direct LLM responses.

4. **Personalization through dual-corpus** — By maintaining separate corpora (city knowledge + user data), the retrieval step naturally surfaces the intersection of "what exists in this city" and "what this specific user would love."

5. **The retrieval layer IS the moat** — The quality of indexed city knowledge (curated, verified, fresh) is what differentiates CityScout from asking ChatGPT. The corpus is the product.

## Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- OpenAI API key (or OpenRouter for proxy)
- Pinecone API key

### Backend

```bash
# Create virtual environment
python -m venv .venv && source .venv/bin/activate

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
| GET | `/api/cities` | List available cities with metadata |
| POST | `/api/ingest` | Start city data ingestion to Pinecone |
| GET | `/api/ingest/status` | Ingestion progress |
| POST | `/api/profile` | Generate taste profile from quiz |
| POST | `/api/profile/upload` | Upload user data (Spotify/YouTube/Maps/IG) |
| GET | `/api/profile/user/{id}` | Check uploaded data status |
| POST | `/api/guide` | Generate personalized guide (dual-corpus RAG) |
| POST | `/api/chat` | Conversational RAG agent |

## Data Format

### City Knowledge (`data/cities/*.json`)

```json
{
  "id": "ba-coffee-01",
  "city": "buenos-aires",
  "category": "coffee",
  "source_type": "reddit",
  "source_url": "https://reddit.com/r/BuenosAires/comments/...",
  "date": "2024-11-15",
  "text": "Best specialty coffee in Buenos Aires — LAB Tostadores in Palermo...",
  "venues": [
    {
      "name": "LAB Tostadores",
      "lat": -34.5875,
      "lng": -58.4324,
      "neighborhood": "Palermo Hollywood"
    }
  ]
}
```

### User Data (`data/sample-user/`)

Sample exports for demo mode: `spotify-history.json`, `youtube-subscriptions.json`, `maps-saved-places.json`

## Testing

```bash
cd api
python -m pytest tests/test_rag.py -v
```

**39 tests** covering:
- Text chunking strategy (overlap, edge cases)
- City data loading and validation
- Source-specific parsers (Spotify, YouTube, Maps, Instagram)
- User data upload endpoint
- Dual-corpus RAG retrieval
- Profile generation (mocked)
- Guide generation with citations (mocked)
- RAGAS evaluation structure
- API endpoint availability
- Data quality validation (minimum chunks, realistic text, category diversity)

## License

MIT
