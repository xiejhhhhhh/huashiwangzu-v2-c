"""Seed dictionary service — loads built-in dictionary config and provides lookups."""

import re
from app.services.knowledge import defaults


def get_all_brands() -> dict[str, dict]:
    return dict(defaults.BRANDS)


def get_brand_aliases() -> dict[str, list[str]]:
    return dict(defaults.BRAND_ALIASES)


def is_brand(name: str) -> bool:
    clean = name.strip()
    if clean in defaults.BRANDS:
        return True
    for standard, aliases in defaults.BRAND_ALIASES.items():
        if clean in aliases or clean == standard:
            return True
    return False


def resolve_brand(alias: str) -> str | None:
    """Resolve an alias to its standard brand name."""
    clean = alias.strip()
    if clean in defaults.BRANDS:
        return clean
    for standard, aliases in defaults.BRAND_ALIASES.items():
        if clean in aliases:
            return standard
    return None


def get_entity_types() -> list[str]:
    return list(defaults.ENTITY_TYPES)


def is_valid_entity_type(t: str) -> bool:
    return t in defaults.ENTITY_TYPES


def is_transition_concept(word: str) -> bool:
    return word.strip() in defaults.TRANSITION_CONCEPT_WHITELIST


def is_stop_word(word: str) -> bool:
    return word.strip() in defaults.STOP_WORDS


def is_process_word(word: str) -> bool:
    return word.strip() in defaults.PROCESS_WORDS


def is_organization(name: str) -> bool:
    return any(name.strip().endswith(suf) for suf in defaults.ORG_SUFFIXES)


def is_doc_type(word: str) -> bool:
    return word.strip() in defaults.DOC_TYPES


def get_llm_allowed_types() -> list[str]:
    return list(defaults.LLM_ALLOWED_TYPES)


def is_llm_type_blocked(t: str) -> bool:
    return t in defaults.LLM_BLOCKED_TYPES


def is_known_entity(name: str, db_standard_names: set[str] | None = None) -> bool:
    """Check against built-in + optional DB entities."""
    clean = name.strip()
    if is_brand(clean) or is_transition_concept(clean) or is_doc_type(clean):
        return True
    if db_standard_names and clean in db_standard_names:
        return True
    return False
