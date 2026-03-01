"""
TDD tests for CityScout RAG pipeline.
Tests cover: chunking, data loading, profile generation, guide generation,
parsers, user data upload, dual-corpus RAG, and RAGAS evaluation.
"""

import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path so we can import server modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Test: Chunking ──


class TestChunking:
    """Test the text chunking strategy."""

    def test_short_text_no_split(self):
        from server import chunk_text

        text = "This is a short text that should not be split."
        chunks = chunk_text(text, max_words=400)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_long_text_splits(self):
        from server import chunk_text

        text = " ".join(["word"] * 800)
        chunks = chunk_text(text, max_words=400, overlap=50)
        assert len(chunks) > 1
        for c in chunks:
            assert len(c.split()) <= 400

    def test_overlap_works(self):
        from server import chunk_text

        words = [f"word{i}" for i in range(100)]
        text = " ".join(words)
        chunks = chunk_text(text, max_words=60, overlap=10)
        assert len(chunks) >= 2
        chunk1_words = chunks[0].split()
        chunk2_words = chunks[1].split()
        assert chunk1_words[-10:] == chunk2_words[:10]

    def test_empty_text(self):
        from server import chunk_text

        chunks = chunk_text("", max_words=400)
        assert chunks == []


# ── Test: City Data Loading ──


class TestCityDataLoading:
    """Test loading and processing city data files."""

    def test_load_buenos_aires(self):
        from server import load_city_data

        chunks = load_city_data("buenos-aires")
        assert len(chunks) > 0
        for chunk in chunks:
            assert "id" in chunk
            assert "text" in chunk
            assert "metadata" in chunk
            assert "city" in chunk["metadata"]
            assert "category" in chunk["metadata"]
            assert chunk["metadata"]["city"] == "buenos-aires"

    def test_load_all_cities(self):
        from server import load_city_data, CITIES_DIR

        for fp in CITIES_DIR.glob("*.json"):
            city_slug = fp.stem
            chunks = load_city_data(city_slug)
            assert len(chunks) > 0, f"No chunks for {city_slug}"
            print(f"  {city_slug}: {len(chunks)} chunks")

    def test_metadata_categories(self):
        from server import load_city_data

        chunks = load_city_data("buenos-aires")
        categories = set(c["metadata"]["category"] for c in chunks)
        assert len(categories) >= 4, f"Only {len(categories)} categories: {categories}"
        print(f"  Categories: {categories}")

    def test_nonexistent_city_raises(self):
        from server import load_city_data

        with pytest.raises(FileNotFoundError):
            load_city_data("nonexistent-city")

    def test_chunk_has_source_info(self):
        from server import load_city_data

        chunks = load_city_data("barcelona")
        for chunk in chunks:
            assert chunk["metadata"]["source_url"], f"Missing source_url in {chunk['id']}"
            assert chunk["metadata"]["source_type"], f"Missing source_type in {chunk['id']}"


# ── Test: Available Cities ──


class TestAvailableCities:
    """Test the city discovery function."""

    def test_get_cities_returns_list(self):
        from server import get_available_cities

        cities = get_available_cities()
        assert isinstance(cities, list)
        assert len(cities) >= 3

    def test_city_has_metadata(self):
        from server import get_available_cities

        cities = get_available_cities()
        for city in cities:
            assert "slug" in city
            assert "name" in city
            assert "chunk_count" in city
            assert "categories" in city
            assert city["chunk_count"] > 0

    def test_city_names_formatted(self):
        from server import get_available_cities

        cities = get_available_cities()
        slugs = [c["slug"] for c in cities]
        assert "buenos-aires" in slugs
        ba = next(c for c in cities if c["slug"] == "buenos-aires")
        assert ba["name"] == "Buenos Aires"


# ── Test: Profile Generation (mocked) ──


class TestProfileGeneration:
    """Test profile generation from quiz answers."""

    @patch("server.openai_client")
    def test_profile_format(self, mock_openai):
        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(
                message=MagicMock(
                    content="You're a specialty coffee devotee who loves hole-in-the-wall restaurants and underground music venues."
                )
            )
        ]
        mock_completion.usage = MagicMock(
            prompt_tokens=100, completion_tokens=50, total_tokens=150
        )
        mock_openai.chat.completions.create.return_value = mock_completion

        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/api/profile",
            json={
                "quiz_answers": {
                    "coffee": "Specialty pour-over",
                    "food": "Street food and hole-in-the-wall",
                    "activity": "Walking and exploring",
                    "nightlife": "Live music and bars",
                    "neighborhood": "Artsy and bohemian",
                    "budget": "Mid-range",
                }
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "profile" in data
        assert len(data["profile"]) > 20
        assert "usage" in data


# ── Test: Guide Generation (mocked) ──


class TestGuideGeneration:
    """Test the guide generation RAG pipeline."""

    @patch("server.pc")
    @patch("server.openai_client")
    def test_guide_has_citations(self, mock_openai, mock_pc):
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )
        mock_match = MagicMock()
        mock_match.id = "ba-coffee-01"
        mock_match.score = 0.92
        mock_match.metadata = {
            "text": "LAB Tostadores de Café in Chacarita. They roast on-site.",
            "city": "buenos-aires",
            "category": "coffee",
            "source_url": "https://reddit.com/r/BuenosAires/comments/abc123",
            "source_type": "reddit",
            "date": "2024-11-15",
        }
        mock_index = MagicMock()
        mock_index.query.return_value = MagicMock(matches=[mock_match])
        mock_pc.Index.return_value = mock_index

        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(
                message=MagicMock(
                    content="## Coffee\n\n**LAB Tostadores** (Chacarita)\nPerfect for you because...\n[Source: reddit - https://reddit.com/r/BuenosAires/comments/abc123]"
                )
            )
        ]
        mock_completion.usage = MagicMock(
            prompt_tokens=500, completion_tokens=200, total_tokens=700
        )
        mock_openai.chat.completions.create.return_value = mock_completion

        from server import app
        from fastapi.testclient import TestClient

        with patch("server.score_with_ragas", return_value={"faithfulness": 0.9, "context_precision": 0.85, "relevancy": 0.88}):
            client = TestClient(app)
            resp = client.post(
                "/api/guide",
                json={
                    "profile": "You're a specialty coffee devotee.",
                    "city": "buenos-aires",
                    "top_k": 5,
                },
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "guide" in data
        assert "sources" in data
        assert "scores" in data
        assert len(data["sources"]) > 0
        assert "Source" in data["guide"] or "source" in data["guide"].lower()


# ── Test: RAGAS Evaluation (structure) ──


class TestRagasEvaluation:
    """Test RAGAS evaluation pipeline structure."""

    def test_score_label_good(self):
        from server import _score_label

        assert "GOOD" in _score_label(0.9)
        assert "GOOD" in _score_label(0.8)

    def test_score_label_ok(self):
        from server import _score_label

        assert "OK" in _score_label(0.6)
        assert "OK" in _score_label(0.5)

    def test_score_label_low(self):
        from server import _score_label

        assert "LOW" in _score_label(0.3)
        assert "LOW" in _score_label(0.1)

    def test_score_label_none(self):
        from server import _score_label

        assert _score_label(None) == "N/A"


# ── Test: API Endpoints ──


class TestAPIEndpoints:
    """Test basic API endpoint availability."""

    def test_health(self):
        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_cities(self):
        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/cities")
        assert resp.status_code == 200
        data = resp.json()
        assert "cities" in data
        assert len(data["cities"]) >= 3

    def test_ingest_status(self):
        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.get("/api/ingest/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "phase" in data
        assert "running" in data


# ── Test: Data Quality ──


class TestDataQuality:
    """Test that city data files are well-formed and realistic."""

    def test_all_cities_have_minimum_chunks(self):
        from server import CITIES_DIR

        for fp in CITIES_DIR.glob("*.json"):
            data = json.loads(fp.read_text())
            assert len(data) >= 20, f"{fp.stem} has only {len(data)} chunks (need ≥20)"

    def test_chunks_have_realistic_text(self):
        from server import CITIES_DIR

        for fp in CITIES_DIR.glob("*.json"):
            data = json.loads(fp.read_text())
            for item in data:
                text = item.get("text", "")
                assert len(text) >= 100, f"Chunk {item.get('id')} in {fp.stem} too short: {len(text)} chars"
                assert len(text.split()) >= 20, f"Chunk {item.get('id')} in {fp.stem} has too few words"

    def test_source_types_valid(self):
        from server import CITIES_DIR

        valid_types = {"reddit", "blog", "local_tip"}
        for fp in CITIES_DIR.glob("*.json"):
            data = json.loads(fp.read_text())
            for item in data:
                assert item.get("source_type") in valid_types, (
                    f"Invalid source_type '{item.get('source_type')}' in {item.get('id')}"
                )

    def test_categories_diverse(self):
        from server import CITIES_DIR

        for fp in CITIES_DIR.glob("*.json"):
            data = json.loads(fp.read_text())
            categories = set(item.get("category") for item in data)
            assert len(categories) >= 4, (
                f"{fp.stem} has only {len(categories)} categories: {categories}"
            )


# ══════════════════════════════════════════════════════════════════════
# NEW: Multi-source data upload & dual-corpus RAG tests
# ══════════════════════════════════════════════════════════════════════


# ── Test: Parsers ──


class TestParsers:
    """Test each data source parser with sample data."""

    def _load_sample(self, filename: str) -> dict:
        """Load a sample data file."""
        sample_dir = Path(__file__).resolve().parent.parent.parent / "data" / "sample-user"
        fp = sample_dir / filename
        assert fp.exists(), f"Sample file not found: {fp}"
        return json.loads(fp.read_text())

    def test_parse_spotify(self):
        from parsers import parse_spotify

        data = self._load_sample("spotify-history.json")
        chunks = parse_spotify(data)

        assert len(chunks) >= 3, f"Expected ≥3 chunks, got {len(chunks)}"

        # Check chunk structure
        for chunk in chunks:
            assert "text" in chunk
            assert "metadata" in chunk
            assert chunk["metadata"]["source_type"] == "spotify"
            assert chunk["metadata"]["category"] in (
                "music_taste", "genre_preferences", "mood_energy", "lifestyle_patterns"
            )
            assert chunk["metadata"]["signal_type"]
            assert len(chunk["text"]) > 20

        # Verify specific signals
        all_text = " ".join(c["text"] for c in chunks)
        assert "Miles Davis" in all_text or "jazz" in all_text.lower()
        print(f"  Spotify: {len(chunks)} chunks parsed")

    def test_parse_youtube(self):
        from parsers import parse_youtube

        data = self._load_sample("youtube-subscriptions.json")
        chunks = parse_youtube(data)

        assert len(chunks) >= 2, f"Expected ≥2 chunks, got {len(chunks)}"

        for chunk in chunks:
            assert chunk["metadata"]["source_type"] == "youtube"
            assert chunk["metadata"]["category"] in (
                "content_interests", "watch_patterns", "travel_interests"
            )

        all_text = " ".join(c["text"] for c in chunks)
        assert "coffee" in all_text.lower() or "food" in all_text.lower() or "travel" in all_text.lower()
        print(f"  YouTube: {len(chunks)} chunks parsed")

    def test_parse_google_maps(self):
        from parsers import parse_google_maps

        data = self._load_sample("maps-saved-places.json")
        chunks = parse_google_maps(data)

        assert len(chunks) >= 3, f"Expected ≥3 chunks, got {len(chunks)}"

        for chunk in chunks:
            assert chunk["metadata"]["source_type"] == "google_maps"
            assert chunk["metadata"]["category"] in (
                "place_preferences", "food_preferences", "neighborhood_vibes",
                "budget_signals", "venue_features"
            )

        all_text = " ".join(c["text"] for c in chunks)
        assert "Palermo" in all_text or "restaurant" in all_text.lower() or "cafe" in all_text.lower()
        print(f"  Google Maps: {len(chunks)} chunks parsed")

    def test_parse_instagram(self):
        from parsers import parse_instagram

        # Use inline sample since we don't have a separate file
        data = {
            "saved_posts": [
                {"caption": "Amazing coffee at this hidden gem", "category": "food",
                 "hashtags": ["coffee", "caffeineaddict", "specialtycoffee"],
                 "location": "Palermo Soho", "media_type": "image"},
                {"caption": "Gallery opening tonight", "category": "art",
                 "hashtags": ["contemporaryart", "gallery", "buenosaires"],
                 "location": "La Boca", "media_type": "image"},
                {"caption": "Wine and jazz kind of evening", "category": "nightlife",
                 "hashtags": ["naturalwine", "jazzbar", "nightout"],
                 "location": "San Telmo", "media_type": "image"},
                {"caption": "Architecture walk through Recoleta", "category": "travel",
                 "hashtags": ["architecture", "design", "travel"],
                 "location": "Recoleta", "media_type": "image"},
            ],
            "liked_posts": [
                {"caption": "Best street food in the city", "category": "food",
                 "hashtags": ["streetfood", "foodie"]},
                {"caption": "Sunset from the rooftop bar", "category": "nightlife",
                 "hashtags": ["cocktails", "bar", "sunset"]},
            ],
        }
        chunks = parse_instagram(data)

        assert len(chunks) >= 2, f"Expected ≥2 chunks, got {len(chunks)}"

        for chunk in chunks:
            assert chunk["metadata"]["source_type"] == "instagram"
            assert chunk["metadata"]["category"] in (
                "aesthetic_preferences", "interest_signals", "location_preferences",
                "lifestyle_signals"
            )

        print(f"  Instagram: {len(chunks)} chunks parsed")

    def test_parser_router(self):
        from parsers import parse_user_data

        data = {"streaming_history": [], "top_artists": []}
        chunks = parse_user_data("spotify", data)
        assert isinstance(chunks, list)

    def test_parser_unknown_source(self):
        from parsers import parse_user_data

        with pytest.raises(ValueError, match="Unknown source"):
            parse_user_data("tiktok", {})

    def test_parser_empty_data(self):
        from parsers import parse_spotify, parse_youtube, parse_google_maps, parse_instagram

        assert parse_spotify({}) == []
        assert parse_youtube({}) == []
        assert parse_google_maps({}) == []
        assert parse_instagram({}) == []


# ── Test: User Data Upload Endpoint ──


class TestUserDataUpload:
    """Test the /api/profile/upload endpoint."""

    @patch("server.pc")
    @patch("server.openai_client")
    def test_upload_spotify(self, mock_openai, mock_pc):
        """Test uploading Spotify data."""
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536) for _ in range(10)]
        )
        mock_index = MagicMock()
        mock_pc.Index.return_value = mock_index

        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        sample_dir = Path(__file__).resolve().parent.parent.parent / "data" / "sample-user"
        spotify_data = json.loads((sample_dir / "spotify-history.json").read_text())

        resp = client.post("/api/profile/upload", json={
            "source": "spotify",
            "data": spotify_data,
            "user_id": "test-user-1",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] == "test-user-1"
        assert data["source"] == "spotify"
        assert data["chunks_stored"] > 0
        assert "signal_types" in data
        assert "signals" in data
        print(f"  → Stored {data['chunks_stored']} chunks, types: {data['signal_types']}")

    @patch("server.pc")
    @patch("server.openai_client")
    def test_upload_google_maps(self, mock_openai, mock_pc):
        """Test uploading Google Maps data."""
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536) for _ in range(10)]
        )
        mock_index = MagicMock()
        mock_pc.Index.return_value = mock_index

        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)

        sample_dir = Path(__file__).resolve().parent.parent.parent / "data" / "sample-user"
        maps_data = json.loads((sample_dir / "maps-saved-places.json").read_text())

        resp = client.post("/api/profile/upload", json={
            "source": "google_maps",
            "data": maps_data,
            "user_id": "test-user-2",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "google_maps"
        assert data["chunks_stored"] > 0

    def test_upload_invalid_source(self):
        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/api/profile/upload", json={
            "source": "tiktok",
            "data": {},
        })
        assert resp.status_code == 400
        assert "Unknown source" in resp.json()["detail"]

    @patch("server.pc")
    @patch("server.openai_client")
    def test_upload_generates_user_id(self, mock_openai, mock_pc):
        """Test that user_id is auto-generated when not provided."""
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536) for _ in range(10)]
        )
        mock_index = MagicMock()
        mock_pc.Index.return_value = mock_index

        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/api/profile/upload", json={
            "source": "spotify",
            "data": {
                "streaming_history": [
                    {"master_metadata_album_artist_name": "Test Artist",
                     "master_metadata_track_name": "Test Song",
                     "ms_played": 180000}
                ],
                "top_artists": [{"name": "Test Artist", "genres": ["rock"]}],
            },
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "user_id" in data
        assert len(data["user_id"]) > 0


# ── Test: Dual-Corpus RAG ──


class TestDualCorpusRAG:
    """Test that guide generation uses both city and user corpora."""

    @patch("server.pc")
    @patch("server.openai_client")
    def test_guide_with_user_id(self, mock_openai, mock_pc):
        """Test guide generation with user data (dual-corpus)."""
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )

        # City match
        city_match = MagicMock()
        city_match.id = "ba-coffee-01"
        city_match.score = 0.92
        city_match.metadata = {
            "text": "LAB Tostadores in Chacarita serves specialty coffee.",
            "city": "buenos-aires",
            "category": "coffee",
            "source_url": "https://reddit.com/r/test",
            "source_type": "reddit",
            "date": "2024-11-15",
        }

        # User signal match
        user_match = MagicMock()
        user_match.id = "user_test-jazz-0"
        user_match.score = 0.88
        user_match.metadata = {
            "text": "User's top Spotify artists: Miles Davis, Tom Jobim. Heavy jazz and bossa nova listener.",
            "signal_type": "top_artists",
            "category": "music_taste",
            "source_type": "spotify",
        }

        mock_index = MagicMock()
        # First call (city query), second call (category queries), third call (user namespace)
        mock_index.query.side_effect = [
            MagicMock(matches=[city_match]),     # city query
            MagicMock(matches=[]),                # category: coffee
            MagicMock(matches=[]),                # category: food
            MagicMock(matches=[]),                # category: nightlife
            MagicMock(matches=[]),                # category: culture
            MagicMock(matches=[user_match]),      # user namespace query
        ]
        mock_pc.Index.return_value = mock_index

        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(
                message=MagicMock(
                    content="## Coffee\n\n**LAB Tostadores** (Chacarita)\nBased on your Spotify showing heavy jazz...\n[Source: reddit - https://reddit.com/r/test]"
                )
            )
        ]
        mock_completion.usage = MagicMock(
            prompt_tokens=800, completion_tokens=300, total_tokens=1100
        )
        mock_openai.chat.completions.create.return_value = mock_completion

        from server import app, user_data_store
        from fastapi.testclient import TestClient

        # Register user in data store so guide knows user has data
        user_data_store["test-dual"] = {"sources": ["spotify"], "chunk_count": 3, "signals": []}

        with patch("server.score_with_ragas", return_value={
            "faithfulness": 0.9, "context_precision": 0.85, "relevancy": 0.88
        }):
            client = TestClient(app)
            resp = client.post("/api/guide", json={
                "profile": "Jazz and bossa nova lover",
                "city": "buenos-aires",
                "top_k": 5,
                "user_id": "test-dual",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["enhanced"] is True
        assert data["user_signals"] is not None
        assert len(data["user_signals"]) > 0
        assert data["user_signals"][0]["source_type"] == "spotify"
        print(f"  → Enhanced guide: {len(data['guide'])} chars, {len(data['user_signals'])} user signals")

    @patch("server.pc")
    @patch("server.openai_client")
    def test_guide_without_user_id(self, mock_openai, mock_pc):
        """Test guide generation without user data (standard path)."""
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )

        city_match = MagicMock()
        city_match.id = "ba-food-01"
        city_match.score = 0.90
        city_match.metadata = {
            "text": "El Preferido de Palermo serves traditional Argentine food.",
            "city": "buenos-aires",
            "category": "food",
            "source_url": "https://reddit.com/r/test",
            "source_type": "reddit",
            "date": "2024-11-15",
        }

        mock_index = MagicMock()
        mock_index.query.return_value = MagicMock(matches=[city_match])
        mock_pc.Index.return_value = mock_index

        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="## Food\n\n**El Preferido** (Palermo)\n..."))
        ]
        mock_completion.usage = MagicMock(
            prompt_tokens=500, completion_tokens=200, total_tokens=700
        )
        mock_openai.chat.completions.create.return_value = mock_completion

        from server import app
        from fastapi.testclient import TestClient

        with patch("server.score_with_ragas", return_value={
            "faithfulness": 0.85, "context_precision": 0.80, "relevancy": 0.82
        }):
            client = TestClient(app)
            resp = client.post("/api/guide", json={
                "profile": "A food lover.",
                "city": "buenos-aires",
                "top_k": 5,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["enhanced"] is False
        assert data["user_signals"] is None
        print(f"  → Standard guide: {len(data['guide'])} chars")

    @patch("server.pc")
    @patch("server.openai_client")
    def test_enhanced_prompt_used_when_user_data(self, mock_openai, mock_pc):
        """Verify that the enhanced prompt is used when user data is available."""
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )

        city_match = MagicMock()
        city_match.id = "ba-01"
        city_match.score = 0.9
        city_match.metadata = {
            "text": "Some city content.",
            "city": "buenos-aires",
            "category": "coffee",
            "source_url": "https://example.com",
            "source_type": "reddit",
            "date": "2024-01-01",
        }

        user_match = MagicMock()
        user_match.id = "user-01"
        user_match.score = 0.85
        user_match.metadata = {
            "text": "User likes jazz.",
            "signal_type": "genres",
            "category": "genre_preferences",
            "source_type": "spotify",
        }

        mock_index = MagicMock()
        mock_index.query.side_effect = [
            MagicMock(matches=[city_match]),
            MagicMock(matches=[]),
            MagicMock(matches=[]),
            MagicMock(matches=[]),
            MagicMock(matches=[]),
            MagicMock(matches=[user_match]),
        ]
        mock_pc.Index.return_value = mock_index

        mock_completion = MagicMock()
        mock_completion.choices = [MagicMock(message=MagicMock(content="Guide content"))]
        mock_completion.usage = MagicMock(prompt_tokens=500, completion_tokens=200, total_tokens=700)
        mock_openai.chat.completions.create.return_value = mock_completion

        from server import app, user_data_store
        from fastapi.testclient import TestClient

        user_data_store["test-prompt"] = {"sources": ["spotify"], "chunk_count": 1, "signals": []}

        with patch("server.score_with_ragas", return_value={
            "faithfulness": 0.9, "context_precision": 0.85, "relevancy": 0.88
        }):
            client = TestClient(app)
            resp = client.post("/api/guide", json={
                "profile": "Jazz lover",
                "city": "buenos-aires",
                "top_k": 5,
                "user_id": "test-prompt",
            })

        assert resp.status_code == 200

        # Verify the LLM was called with the enhanced prompt
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        system_content = messages[0]["content"]
        user_content = messages[1]["content"]

        # Enhanced system prompt should mention "TWO sources"
        assert "TWO sources" in system_content or "Digital Platform" in user_content
        print("  → Verified enhanced prompt used for dual-corpus RAG")


# ── Test: Chat Endpoint ──


class TestChatEndpoint:
    """Test the /api/chat conversational RAG endpoint."""

    @patch("server.pc")
    @patch("server.openai_client")
    def test_chat_basic(self, mock_openai, mock_pc):
        """Test basic chat endpoint with a simple question."""
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )

        city_match = MagicMock()
        city_match.id = "ba-coffee-01"
        city_match.score = 0.90
        city_match.metadata = {
            "text": "LAB Tostadores de Café in Chacarita is great for specialty coffee.",
            "city": "buenos-aires",
            "category": "coffee",
            "source_url": "https://reddit.com/r/test",
            "source_type": "reddit",
            "date": "2024-11-15",
            "venues_json": "",
        }

        mock_index = MagicMock()
        mock_index.query.return_value = MagicMock(matches=[city_match])
        mock_pc.Index.return_value = mock_index

        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(
                message=MagicMock(
                    content="**LAB Tostadores de Café** in Chacarita is perfect for you!\n\nVENUE: LAB Tostadores de Café | coffee | -34.5875 | -58.4545 | Amazing specialty pour-overs in a minimal space"
                )
            )
        ]
        mock_completion.usage = MagicMock(
            prompt_tokens=300, completion_tokens=100, total_tokens=400
        )
        mock_openai.chat.completions.create.return_value = mock_completion

        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/api/chat", json={
            "message": "Where can I get good coffee?",
            "city": "buenos-aires",
            "profile": "A specialty coffee lover.",
            "history": [],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data
        assert "recommendations" in data
        assert len(data["message"]) > 0
        # VENUE lines should be stripped from message
        assert "VENUE:" not in data["message"]
        # But parsed into recommendations
        assert len(data["recommendations"]) >= 1
        assert data["recommendations"][0]["name"] == "LAB Tostadores de Café"
        assert data["recommendations"][0]["category"] == "coffee"
        assert data["recommendations"][0]["lat"] == -34.5875
        print(f"  → Chat response: {len(data['message'])} chars, {len(data['recommendations'])} recs")

    @patch("server.pc")
    @patch("server.openai_client")
    def test_chat_with_history(self, mock_openai, mock_pc):
        """Test chat endpoint preserves conversation history."""
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )

        mock_index = MagicMock()
        mock_index.query.return_value = MagicMock(matches=[])
        mock_pc.Index.return_value = mock_index

        mock_completion = MagicMock()
        mock_completion.choices = [
            MagicMock(message=MagicMock(content="Based on our earlier discussion about coffee, let me suggest..."))
        ]
        mock_completion.usage = MagicMock(
            prompt_tokens=500, completion_tokens=80, total_tokens=580
        )
        mock_openai.chat.completions.create.return_value = mock_completion

        from server import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/api/chat", json={
            "message": "Tell me more",
            "city": "barcelona",
            "profile": "A culture enthusiast.",
            "history": [
                {"role": "user", "content": "Where can I get coffee?"},
                {"role": "assistant", "content": "Try Satan's Coffee Corner!"},
            ],
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "message" in data

        # Verify conversation history was passed to LLM
        call_args = mock_openai.chat.completions.create.call_args
        messages = call_args.kwargs.get("messages") or call_args[1].get("messages")
        # Should have: system + 2 history messages + 1 current message = 4
        assert len(messages) >= 4


# ── Test: City Data Coordinates ──


class TestCityCoordinates:
    """Test that city data files include realistic coordinates."""

    def test_all_cities_have_coordinates(self):
        from server import CITIES_DIR

        for fp in CITIES_DIR.glob("*.json"):
            data = json.loads(fp.read_text())
            coords_count = 0
            for item in data:
                if item.get("coordinates") and item.get("venue_name"):
                    coords_count += 1
                    coords = item["coordinates"]
                    assert "lat" in coords, f"Missing lat in {item.get('id')}"
                    assert "lng" in coords, f"Missing lng in {item.get('id')}"
                    assert isinstance(coords["lat"], (int, float))
                    assert isinstance(coords["lng"], (int, float))

            assert coords_count > 0, f"{fp.stem} has no items with coordinates"
            print(f"  {fp.stem}: {coords_count}/{len(data)} chunks have coordinates")

    def test_coordinates_realistic_ranges(self):
        """Test that coordinates are within realistic ranges for each city."""
        from server import CITIES_DIR

        city_bounds = {
            "buenos-aires": {"lat": (-34.7, -34.5), "lng": (-58.6, -58.3)},
            "barcelona": {"lat": (41.3, 41.5), "lng": (2.0, 2.3)},
            "lisbon": {"lat": (38.6, 38.8), "lng": (-9.3, -9.0)},
        }

        for fp in CITIES_DIR.glob("*.json"):
            city_slug = fp.stem
            if city_slug not in city_bounds:
                continue
            bounds = city_bounds[city_slug]
            data = json.loads(fp.read_text())

            for item in data:
                coords = item.get("coordinates")
                if not coords:
                    continue

                lat, lng = coords["lat"], coords["lng"]
                lat_range = bounds["lat"]
                lng_range = bounds["lng"]

                assert lat_range[0] <= lat <= lat_range[1], (
                    f"{item.get('id')}: lat {lat} out of range {lat_range}"
                )
                assert lng_range[0] <= lng <= lng_range[1], (
                    f"{item.get('id')}: lng {lng} out of range {lng_range}"
                )

    def test_venue_names_present(self):
        """Test that chunks with coordinates have venue names."""
        from server import CITIES_DIR

        for fp in CITIES_DIR.glob("*.json"):
            data = json.loads(fp.read_text())
            for item in data:
                if item.get("coordinates"):
                    assert item.get("venue_name"), (
                        f"{item.get('id')} has coordinates but no venue_name"
                    )
                    assert len(item["venue_name"]) > 2


# ── Test: VENUE Line Parsing ──


class TestVenueLineParsing:
    """Test parsing VENUE: lines from LLM responses."""

    def test_parse_single_venue(self):
        from server import parse_venue_lines

        text = "Some text\nVENUE: Café Central | coffee | -34.5875 | -58.4124 | Great pour-overs\nMore text"
        venues = parse_venue_lines(text)
        assert len(venues) == 1
        assert venues[0]["name"] == "Café Central"
        assert venues[0]["category"] == "coffee"
        assert venues[0]["lat"] == -34.5875
        assert venues[0]["lng"] == -58.4124

    def test_parse_multiple_venues(self):
        from server import parse_venue_lines

        text = """Here are my recommendations:
VENUE: Café A | coffee | 41.3825 | 2.1745 | Amazing espresso
VENUE: Bar B | nightlife | 41.3800 | 2.1758 | Jazz nightly
Some more text here."""
        venues = parse_venue_lines(text)
        assert len(venues) == 2
        assert venues[0]["name"] == "Café A"
        assert venues[1]["category"] == "nightlife"

    def test_parse_no_venues(self):
        from server import parse_venue_lines

        text = "Just a regular response with no venue lines."
        venues = parse_venue_lines(text)
        assert len(venues) == 0

    def test_parse_malformed_venue_ignored(self):
        from server import parse_venue_lines

        text = "VENUE: incomplete\nVENUE: Good One | food | 38.7107 | -9.1410 | Tasty"
        venues = parse_venue_lines(text)
        assert len(venues) == 1
        assert venues[0]["name"] == "Good One"
