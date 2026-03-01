"""
TDD tests for CityScout RAG pipeline.
Tests cover: chunking, data loading, profile generation, guide generation, and RAGAS evaluation.
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

        # Create a text with 800 words
        text = " ".join(["word"] * 800)
        chunks = chunk_text(text, max_words=400, overlap=50)
        assert len(chunks) > 1
        # Each chunk should have at most 400 words
        for c in chunks:
            assert len(c.split()) <= 400

    def test_overlap_works(self):
        from server import chunk_text

        words = [f"word{i}" for i in range(100)]
        text = " ".join(words)
        chunks = chunk_text(text, max_words=60, overlap=10)
        # Chunks should overlap by 10 words
        assert len(chunks) >= 2
        chunk1_words = chunks[0].split()
        chunk2_words = chunks[1].split()
        # Last 10 words of chunk 1 should be first 10 words of chunk 2
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
        # Each chunk should have required fields
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
        # Should have diverse categories
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
        assert len(cities) >= 3  # We created 3 city files

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
        """Profile should be a non-empty string describing the user."""
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
        """Generated guide should include source citations."""
        # Mock embedding
        mock_openai.embeddings.create.return_value = MagicMock(
            data=[MagicMock(embedding=[0.1] * 1536)]
        )
        # Mock Pinecone query
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

        # Mock LLM response
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
        # Guide should contain source reference
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
                # Text should be substantive
                assert len(text) >= 100, f"Chunk {item.get('id')} in {fp.stem} too short: {len(text)} chars"
                # Should contain actual recommendations (place names, etc.)
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
