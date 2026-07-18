"""Runtime-capsule persistence rules for reviewed project recipes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tmcp_runtime.storage.runtime_capsule_persistence import (
    restore_runtime_capsule,
    runtime_capsule_hash_paths,
    runtime_capsule_restored_literal_count,
    runtime_capsule_sha256_literals,
)


RUNTIME_CAPSULE_BOUND = "bound"
RUNTIME_CAPSULE_LEGACY_UNBOUND = "legacy_unbound"
_PREFIX = ("composition_recipe", "runtime_capsule")


class RecipeRuntimeCapsuleError(ValueError):
    """Raised when a stored recipe cannot safely retain runtime provenance."""


def recipe_runtime_capsule_hash_paths() -> tuple[tuple[str, ...], ...]:
    return runtime_capsule_hash_paths(_PREFIX)


def recipe_runtime_capsule_sha256_literals(
    recipe: Mapping[str, Any]
) -> dict[tuple[str | int, ...], str]:
    capsule = recipe.get("runtime_capsule")
    if not isinstance(capsule, Mapping):
        return {}
    return runtime_capsule_sha256_literals(capsule, prefix=_PREFIX)


def restore_recipe_runtime_capsule_digests(
    literals: Mapping[tuple[str | int, ...], str], payload: dict[str, Any]
) -> int:
    recipe = payload.get("composition_recipe")
    if not isinstance(recipe, dict):
        return 0
    binding = recipe.get("phase_capsule_binding")
    capsule = recipe.get("runtime_capsule")
    if not isinstance(binding, Mapping) or not isinstance(capsule, Mapping):
        return 0
    restored_count = runtime_capsule_restored_literal_count(
        capsule, prefix=_PREFIX, literals=literals
    )
    restored = restore_runtime_capsule(
        recipe,
        binding,
        prefix=_PREFIX,
        literals=literals,
    )
    if restored is None:
        return 0
    recipe["runtime_capsule"] = restored
    return restored_count


def recipe_runtime_capsule_status(
    recipe: Mapping[str, Any],
    binding: Mapping[str, Any],
    *,
    allow_legacy: bool,
) -> str:
    if "runtime_capsule" not in recipe:
        if allow_legacy:
            return RUNTIME_CAPSULE_LEGACY_UNBOUND
        raise RecipeRuntimeCapsuleError("runtime capsule is required for new records.")
    if (
        restore_runtime_capsule(
            recipe,
            binding,
            prefix=_PREFIX,
            literals=None,
        )
        is None
    ):
        raise RecipeRuntimeCapsuleError("runtime capsule is invalid.")
    return RUNTIME_CAPSULE_BOUND
