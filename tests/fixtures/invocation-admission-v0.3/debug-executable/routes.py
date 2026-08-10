def normalize_route(value: str) -> str:
    return value.lower().replace("_", "-")


if __name__ == "__main__":
    assert normalize_route("AGENT_WORKFLOW") == "agent-workflow"
