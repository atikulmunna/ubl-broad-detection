"""
Runtime helpers for the retail experiment.

This module handles loading optional saved index assets so the analyzer can
use catalog matching when available while safely falling back when not.
"""

from pathlib import Path
from typing import Dict, Tuple

from config.loader import RETAIL_EXPERIMENT_CONFIG
from utils.retail_index import CatalogIndexError, DeterministicPathEmbedder, load_catalog_index


_RUNTIME_INDEX_CACHE = {}


def reset_runtime_index_cache():
    """Clear cached runtime index state, mainly for tests."""
    _RUNTIME_INDEX_CACHE.clear()


def get_runtime_index_components(config: Dict = None, index_loader=load_catalog_index,
                                 embedder_factory=DeterministicPathEmbedder) -> Tuple[object, object, Dict]:
    """
    Return `(index, embedder, status)` for runtime use.

    If saved-index loading is disabled or fails, returns `(None, None, status)`.
    """
    runtime_config = config or RETAIL_EXPERIMENT_CONFIG
    use_saved_index = runtime_config.get("use_saved_index", True)
    index_dir = runtime_config.get("index_dir", "catalog/index")
    cache_key = str(index_dir)

    if not use_saved_index:
        return None, None, {
            "index_used": False,
            "index_status": "disabled",
            "index_dir": cache_key,
        }

    if cache_key in _RUNTIME_INDEX_CACHE:
        return _RUNTIME_INDEX_CACHE[cache_key]

    try:
        index = index_loader(Path(index_dir))
        embedder = embedder_factory(dimension=index.dimension or 16)
        result = (
            index,
            embedder,
            {
                "index_used": index.size > 0,
                "index_status": "loaded" if index.size > 0 else "empty",
                "index_dir": cache_key,
                "index_reference_count": index.size,
                "index_dimension": index.dimension,
            },
        )
    except (CatalogIndexError, FileNotFoundError, OSError):
        result = (
            None,
            None,
            {
                "index_used": False,
                "index_status": "unavailable",
                "index_dir": cache_key,
            },
        )

    _RUNTIME_INDEX_CACHE[cache_key] = result
    return result
