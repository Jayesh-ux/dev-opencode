from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    success: bool
    output: str = ""
    error: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class Tool:
    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=dict)

    async def execute(self, **kwargs) -> ToolResult:
        raise NotImplementedError
