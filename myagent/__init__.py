"""Package root for ADK discovery."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .agent import root_agent as root_agent

__all__ = ["root_agent"]


def __getattr__(name: str):
    if name == "root_agent":
        from .agent import root_agent

        return root_agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
