"""WorkflowContext — thread-safe context propagation for attribution."""
import threading
import uuid
from typing import Optional
from contextlib import contextmanager
from dataclasses import dataclass, field

_local = threading.local()


@dataclass
class ContextData:
    team: str
    feature: str
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_run_id: Optional[str] = None
    business_entity_id: Optional[str] = None
    business_entity_type: Optional[str] = None

    def to_dict(self):
        return {
            "team": self.team,
            "feature": self.feature,
            "workflow_id": self.workflow_id,
            "agent_run_id": self.agent_run_id,
            "business_entity_id": self.business_entity_id,
            "business_entity_type": self.business_entity_type,
        }


class WorkflowContext:
    """
    Context manager that propagates attribution metadata through LLM calls.
    Thread-safe using threading.local() storage.

    Example:
        with WorkflowContext(team="platform", feature="code-review", business_entity_id="PR-456"):
            response = client.chat.completions.create(...)
    """

    def __init__(
        self,
        team: str,
        feature: str,
        workflow_id: Optional[str] = None,
        agent_run_id: Optional[str] = None,
        business_entity_id: Optional[str] = None,
        business_entity_type: Optional[str] = None,
    ):
        self._data = ContextData(
            team=team,
            feature=feature,
            workflow_id=workflow_id or str(uuid.uuid4()),
            agent_run_id=agent_run_id,
            business_entity_id=business_entity_id,
            business_entity_type=business_entity_type,
        )
        self._previous = None

    def __enter__(self):
        self._previous = getattr(_local, "current_context", None)
        _local.current_context = self._data
        return self

    def __exit__(self, *_):
        _local.current_context = self._previous

    @staticmethod
    def current() -> Optional[ContextData]:
        """Get the current active context, if any."""
        return getattr(_local, "current_context", None)

    @staticmethod
    def require() -> ContextData:
        """Get the current context or return an unattributed default."""
        ctx = WorkflowContext.current()
        if ctx:
            return ctx
        return ContextData(team="unattributed", feature="unknown")

    @staticmethod
    def set(
        team: str,
        feature: str,
        workflow_id: Optional[str] = None,
        agent_run_id: Optional[str] = None,
        business_entity_id: Optional[str] = None,
        business_entity_type: Optional[str] = None,
    ):
        """Set context without using context manager (for async code)."""
        _local.current_context = ContextData(
            team=team,
            feature=feature,
            workflow_id=workflow_id or str(uuid.uuid4()),
            agent_run_id=agent_run_id,
            business_entity_id=business_entity_id,
            business_entity_type=business_entity_type,
        )

    @staticmethod
    def clear():
        """Clear the current context."""
        _local.current_context = None