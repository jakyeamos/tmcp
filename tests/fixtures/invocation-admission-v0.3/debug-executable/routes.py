# Smoke-only fixture module; the sibling test_routes.py contains the behavior assert.

def normalize_route(value: str) -> str:
    return value.lower().replace("_", "-")
