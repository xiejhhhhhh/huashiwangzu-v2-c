"""Quality gate rules for entity/attribute/label boundaries.

Ensures only stable entities enter the dictionary,
attributes are "field=value", detection conclusions
go to evidence, and doc-type words become filter tags.
"""

import re
from app.services.knowledge.dictionary.seed import (
    is_stop_word, is_process_word, is_organization,
    is_doc_type, is_transition_concept,
)
from app.services.knowledge.defaults import STOP_WORDS


MIN_ENTITY_LENGTH = 2
MAX_ENTITY_LENGTH = 64


def passes_entity_gate(term: str) -> bool:
    """Check if a term is qualified to become an entity."""
    clean = term.strip()
    if len(clean) < MIN_ENTITY_LENGTH or len(clean) > MAX_ENTITY_LENGTH:
        return False
    if is_stop_word(clean) or is_process_word(clean):
        return False
    if is_doc_type(clean):
        return False
    if re.search(r"[0-9]{4,}", clean):
        return False
    if re.match(r"^[0-9+\-./#()]+$", clean):
        return False
    if is_organization(clean):
        return False
    if is_transition_concept(clean):
        return True
    return True


def is_entity_quality_adjudged(entity_type: str) -> bool:
    """Stable entity types that can enter dictionary."""
    return entity_type in {
        "brand", "product", "kit", "ingredient",
        "efficacy", "organization",
    }


def is_detection_conclusion(term: str) -> bool:
    """Check if a term is a test/conclusion phrase (goes to evidence, not dict)."""
    patterns = [
        r"^产品安全", r"^安全性评价", r"^检测结论", r"^合格$",
        r"符合.*要求", r"^经.*检验.*$", r"^所检项目",
        r"安全.*评价.*合格", r"^所检.*项目.*合格",
        r"^检验.*结论", r"^判定.*$",
    ]
    return any(re.search(p, term) for p in patterns) and len(term) > 4


def should_be_attribute(value: str) -> bool:
    """Check if value looks like a field attribute rather than an entity."""
    org = is_organization(value)
    long_num = bool(re.search(r"[A-Za-z0-9]{8,}", value))
    looks_field = bool(re.match(r".+[:：]\s*.+", value))
    quantity = bool(re.match(r"^\d+\s*[瓶盒套张支个]", value))
    promo = bool(re.search(r"(折上折|赠品|奖励|折扣|优惠|特价)", value))
    return org or long_num or looks_field or quantity or promo


def classify_as_labels(doc_type: str) -> list[str]:
    """Doc-type words should become filter labels, not entities."""
    if is_doc_type(doc_type):
        return [doc_type]
    return []
