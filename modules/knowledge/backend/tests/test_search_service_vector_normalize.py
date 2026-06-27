"""Tests for knowledge search vector normalization."""

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.knowledge.backend.services.search_service import _normalize_vector, cosine_similarity


def test_normalize_vector_accepts_json_string():
    vec = _normalize_vector("[1, 2, 3.5]")
    assert vec == [1.0, 2.0, 3.5]


def test_normalize_vector_rejects_bad_string():
    assert _normalize_vector("not-a-vector") is None


def test_cosine_similarity_handles_string_inputs():
    assert cosine_similarity("[1, 0]", [1, 0]) == 1.0
