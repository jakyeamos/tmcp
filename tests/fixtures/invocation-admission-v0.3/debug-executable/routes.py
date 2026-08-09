def normalize_route(value: str) -> str:
    return value.lower().replace("_", "-")


assert normalize_route("AGENT_WORKFLOW") == "agent-workflow"
