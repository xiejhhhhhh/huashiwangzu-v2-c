from __future__ import annotations

from .base import MediaProvider
from .local_algorithms import LocalAlgorithmProvider
from .small_model import SmallModelProvider
from .vlm import VlmRefineProvider

_PROVIDERS: dict[str, type[MediaProvider]] = {
    "local_algorithms": LocalAlgorithmProvider,
    "small_model": SmallModelProvider,
    "vlm_refine": VlmRefineProvider,
}


def get_provider(layer: str) -> MediaProvider:
    provider_cls = _PROVIDERS.get(layer)
    if provider_cls is None:
        raise ValueError(f"Unknown media intelligence provider layer: {layer}")
    return provider_cls()


def list_providers() -> list[dict[str, str]]:
    return [
        {"layer": layer, "provider_key": provider_cls.provider_key}
        for layer, provider_cls in sorted(_PROVIDERS.items())
    ]
