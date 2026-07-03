"""Tests for knowledge search vector normalization."""

import os
import sys
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "test-secret-for-knowledge-search-vector-normalize")

REPO_ROOT = Path(__file__).resolve().parents[4]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from modules.knowledge.backend.services.search_service import _normalize_vector, cosine_similarity


def test_normalize_vector_accepts_json_string():
    vec = _normalize_vector("[1, 2, 3.5]")
    assert vec == [1.0, 2.0, 3.5]


def test_normalize_vector_rejects_bad_string():
    assert _normalize_vector("not-a-vector") is None


def test_normalize_vector_accepts_tolist_values():
    class ArrayLike:
        def tolist(self):
            return [1, "2", 3.5]

    assert _normalize_vector(ArrayLike()) == [1.0, 2.0, 3.5]


def test_cosine_similarity_handles_string_inputs():
    assert cosine_similarity("[1, 0]", [1, 0]) == 1.0


def test_cosine_similarity_rejects_dimension_mismatch():
    assert cosine_similarity([1, 0, 0], [1, 0]) == 0.0
