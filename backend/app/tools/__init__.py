from app.tools.system_tools import ExecuteCommand, ReadFile, WriteFile, ListDirectory

TOOL_REGISTRY: dict[str, any] = {}

for tool_cls in [ExecuteCommand, ReadFile, WriteFile, ListDirectory]:
    instance = tool_cls()
    TOOL_REGISTRY[instance.name] = instance


def get_tool(name: str):
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "parameters": t.parameters,
        }
        for t in TOOL_REGISTRY.values()
    ]
