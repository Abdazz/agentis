from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    ok: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    retryable: bool = False  # True for transient errors (network, timeout)


@dataclass
class SessionContext:
    session_id: str
    task_id: str
    sandbox_endpoint: str  # http://{container_ip}:{port}
    secrets_accessor: Any = None  # Vault client — wired in Phase 1C


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    input_schema: dict = {}
    output_schema: dict = {}

    @abstractmethod
    async def execute(self, params: dict, session: SessionContext) -> ToolResult:
        ...

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Only validate concrete (non-abstract) subclasses
        if not getattr(cls, "__abstractmethods__", None):
            if not cls.name:
                raise TypeError(f"{cls.__name__} must define 'name'")
            if not cls.description:
                raise TypeError(f"{cls.__name__} must define 'description'")
