"""
Model Registry
Dynamic cache, alias resolution, fuzzy matching, and validation for OpenCode models.
"""

import asyncio
import difflib
import logging
import time
from typing import Dict, List, Optional, Tuple

from ..settings import settings

logger = logging.getLogger(__name__)

# Common aliases mapping short names to full provider/model IDs
DEFAULT_ALIASES: Dict[str, str] = {
    # Anthropic
    "opus": "anthropic/claude-opus-4-5-20251101",
    "claude-opus": "anthropic/claude-opus-4-5-20251101",
    "sonnet": "anthropic/claude-sonnet-4-20250514",
    "claude-sonnet": "anthropic/claude-sonnet-4-20250514",
    "haiku": "anthropic/claude-haiku-4-5-20251001",
    "claude-haiku": "anthropic/claude-haiku-4-5-20251001",
    # Google - always default to Gemini 3 (latest)
    "gemini-flash": "google/gemini-3-flash-preview",
    "gemini-3-flash": "google/gemini-3-flash-preview",
    "gemini3-flash": "google/gemini-3-flash-preview",
    "flash": "google/gemini-3-flash-preview",
    "gemini-pro": "google/gemini-3.1-pro-preview",
    "gemini-3-pro": "google/gemini-3.1-pro-preview",
    "gemini3-pro": "google/gemini-3.1-pro-preview",
    "gemini": "google/gemini-3.1-pro-preview",
    "gemini-3": "google/gemini-3.1-pro-preview",
    "gemini3": "google/gemini-3.1-pro-preview",
    # OpenAI
    "gpt": "openai/gpt-5.4",
    "gpt-5.4": "openai/gpt-5.4",
    "gpt5.4": "openai/gpt-5.4",
    "gpt54": "openai/gpt-5.4",
    "codex": "openai/gpt-5.4",
    "gpt-codex": "openai/gpt-5.4",
    # xAI
    "grok": "xai/grok-3",
    "grok-3": "xai/grok-3",
    # NVIDIA NIM
    "nemotron": "nvidia-nim/nvidia/nemotron-3-super-120b-a12b",
    "nemotron-super": "nvidia-nim/nvidia/nemotron-3-super-120b-a12b",
    "glm5": "nvidia-nim/z-ai/glm5",
    "glm-5.1": "nvidia-nim/z-ai/glm-5.1",
    "glm5.1": "nvidia-nim/z-ai/glm-5.1",
    "deepseek": "nvidia-nim/deepseek-ai/deepseek-v3.2",
    "deepseek-v3": "nvidia-nim/deepseek-ai/deepseek-v3.2",
    "deepseek-v3.2": "nvidia-nim/deepseek-ai/deepseek-v3.2",
}

# Fallback static model list if `opencode models` fails
FALLBACK_MODELS: List[str] = [
    "anthropic/claude-opus-4-5-20251101",
    "anthropic/claude-sonnet-4-20250514",
    "anthropic/claude-haiku-4-5-20251001",
    "google/gemini-3-flash-preview",
    "google/gemini-3.1-pro-preview",
    "openai/gpt-5.4",
    "xai/grok-3",
    "nvidia-nim/nvidia/nemotron-3-super-120b-a12b",
    "nvidia-nim/z-ai/glm5",
    "nvidia-nim/z-ai/glm-5.1",
    "nvidia-nim/deepseek-ai/deepseek-v3.2",
]

# Minimum confidence for fuzzy matching (0.0 - 1.0)
FUZZY_MATCH_THRESHOLD = 0.6


class ModelRegistry:
    """
    Singleton registry for valid OpenCode models.

    Provides:
    - Dynamic caching from `opencode models` CLI output
    - Alias resolution for common short names
    - Fuzzy matching as fallback for typos/incorrect names
    - Validation with resolution chain: exact → alias → fuzzy → default
    """

    _instance: Optional["ModelRegistry"] = None
    _lock = asyncio.Lock()

    def __init__(self):
        self._models: List[str] = []
        self._aliases: Dict[str, str] = dict(DEFAULT_ALIASES)
        self._last_refresh: float = 0
        self._refresh_interval: int = settings.model_cache_ttl
        self._initialized: bool = False

    @classmethod
    async def get_instance(cls) -> "ModelRegistry":
        """Get or create the singleton instance."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset the singleton (for testing)."""
        cls._instance = None

    async def initialize(self) -> None:
        """Initialize the registry by loading models from CLI."""
        if self._initialized and not self._is_stale():
            return
        await self.refresh_models()

    def _is_stale(self) -> bool:
        """Check if the cache needs refreshing."""
        return (time.time() - self._last_refresh) > self._refresh_interval

    async def refresh_models(self) -> None:
        """Refresh the model cache from OpenCode CLI."""
        try:
            from ..opencode_executor import OpenCodeExecutor

            executor = OpenCodeExecutor()
            result = await executor.list_models()

            models = []
            if result.success and result.raw_output:
                for line in result.raw_output.split("\n"):
                    line = line.strip()
                    # Models are in provider/model format
                    if "/" in line and not line.startswith("#") and not line.startswith("-"):
                        # Clean up any extra formatting
                        model_id = line.split()[0] if line.split() else line
                        if "/" in model_id:
                            models.append(model_id)

            if models:
                self._models = models
                self._last_refresh = time.time()
                self._initialized = True
                logger.info(f"Model registry refreshed: {len(models)} models cached")
                logger.debug(f"Cached models: {models}")
            else:
                logger.warning("No models found from CLI, using fallback list")
                self._models = list(FALLBACK_MODELS)
                self._last_refresh = time.time()
                self._initialized = True

        except Exception as e:
            logger.error(f"Failed to refresh models from CLI: {e}")
            if not self._models:
                self._models = list(FALLBACK_MODELS)
                self._initialized = True
            self._last_refresh = time.time()

    def get_cached_models(self) -> List[str]:
        """Get the current list of cached models."""
        return list(self._models) if self._models else list(FALLBACK_MODELS)

    def is_valid_model(self, model: str) -> bool:
        """Check if a model ID is in the valid models list."""
        return model in self._models

    def resolve_alias(self, alias: str) -> Optional[str]:
        """
        Resolve a short alias to a full model ID.

        Args:
            alias: Short model name (e.g., 'opus', 'gemini-flash')

        Returns:
            Full model ID or None if not found
        """
        # Try exact alias match (case-insensitive)
        normalized = alias.lower().strip()
        return self._aliases.get(normalized)

    def find_closest_match(self, invalid_model: str) -> Optional[str]:
        """
        Find the closest matching model using fuzzy matching.

        Uses difflib.get_close_matches for similarity scoring.

        Args:
            invalid_model: The invalid model string to match against

        Returns:
            Closest matching model ID or None if no good match found
        """
        all_candidates = self._models + list(self._aliases.keys())

        matches = difflib.get_close_matches(
            invalid_model.lower(),
            [m.lower() for m in all_candidates],
            n=1,
            cutoff=FUZZY_MATCH_THRESHOLD,
        )

        if not matches:
            return None

        matched_lower = matches[0]

        # Find the original-case version
        for candidate in all_candidates:
            if candidate.lower() == matched_lower:
                # If it's an alias, resolve it
                if candidate.lower() in self._aliases:
                    return self._aliases[candidate.lower()]
                return candidate

        return None

    def validate_and_resolve(self, model: str) -> Tuple[bool, Optional[str], str]:
        """
        Validate a model string and resolve it to a valid model ID.

        Resolution chain:
        1. Exact match against cached models → use as-is
        2. Alias resolution → resolved alias
        3. Fuzzy matching → closest match
        4. None → caller should use default

        Args:
            model: The model string to validate

        Returns:
            Tuple of (is_valid_input, resolved_model, resolution_method)
            - is_valid_input: True if the original input was a valid model
            - resolved_model: The resolved model ID (or None if unresolvable)
            - resolution_method: How it was resolved ('exact', 'alias', 'fuzzy', 'default')
        """
        if not model or not model.strip():
            return False, None, "default"

        model = model.strip()

        # 1. Exact match
        if self.is_valid_model(model):
            return True, model, "exact"

        # 2. Alias resolution
        resolved = self.resolve_alias(model)
        if resolved:
            logger.info(f"Model alias resolved: '{model}' -> '{resolved}'")
            return False, resolved, "alias"

        # 3. Fuzzy matching
        closest = self.find_closest_match(model)
        if closest:
            logger.warning(
                f"Model fuzzy-matched: '{model}' -> '{closest}' "
                f"(original was not a valid model ID)"
            )
            return False, closest, "fuzzy"

        # 4. No match found
        logger.warning(f"Model '{model}' could not be resolved, will use default")
        return False, None, "default"

    def add_alias(self, alias: str, model_id: str) -> None:
        """Add a custom alias mapping."""
        self._aliases[alias.lower().strip()] = model_id

    def get_aliases(self) -> Dict[str, str]:
        """Get all current aliases."""
        return dict(self._aliases)


async def get_model_registry() -> ModelRegistry:
    """
    Get the initialized model registry singleton.

    Ensures the registry is initialized and refreshed if stale.
    """
    registry = await ModelRegistry.get_instance()
    await registry.initialize()
    return registry
