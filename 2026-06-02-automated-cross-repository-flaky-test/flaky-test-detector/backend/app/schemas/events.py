from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum


class CISystem(str, Enum):
    github_actions = "github_actions"
    gitlab_ci = "gitlab_ci"
    jenkins = "jenkins"
    circleci = "circleci"
    unknown = "unknown"


class TestStatus(str, Enum):
    passed = "passed"
    failed = "failed"
    skipped = "skipped"
    error = "error"


class TestExecutionEvent(BaseModel):
    """Canonical test execution event schema — normalized from any CI system."""
    repo: str = Field(..., description="Repository full name (e.g. org/repo)")
    branch: str = Field(default="main")
    commit_sha: Optional[str] = None
    pipeline_id: Optional[str] = None
    test_name: str = Field(..., description="Fully qualified test name")
    test_file: Optional[str] = None
    test_class: Optional[str] = None
    status: TestStatus
    duration_ms: Optional[int] = None
    log_output: Optional[str] = None
    error_message: Optional[str] = None
    stack_trace: Optional[str] = None
    ci_system: CISystem = CISystem.unknown
    environment_vars: Optional[Dict[str, Any]] = None
    timestamp: Optional[datetime] = None

    class Config:
        json_schema_extra = {
            "example": {
                "repo": "myorg/myrepo",
                "branch": "main",
                "commit_sha": "abc123def456",
                "pipeline_id": "run-789",
                "test_name": "tests/test_auth.py::test_user_login",
                "test_file": "tests/test_auth.py",
                "status": "failed",
                "duration_ms": 5234,
                "log_output": "TimeoutError: Expected element to appear within 2000ms",
                "ci_system": "github_actions"
            }
        }


class GitHubActionsWebhook(BaseModel):
    """Adapter schema for GitHub Actions check_run events."""
    action: str
    check_run: Dict[str, Any]
    repository: Dict[str, Any]

    def to_canonical(self) -> list[TestExecutionEvent]:
        """Convert GitHub Actions webhook to canonical events."""
        events = []
        repo = self.repository.get("full_name", "unknown/unknown")
        check_run = self.check_run
        
        # In a real implementation, this would parse the check run output
        # For MVP, we extract what we can
        status = "passed" if check_run.get("conclusion") == "success" else "failed"
        
        events.append(TestExecutionEvent(
            repo=repo,
            branch=check_run.get("head_branch", "main"),
            commit_sha=check_run.get("head_sha"),
            pipeline_id=str(check_run.get("id")),
            test_name=check_run.get("name", "unknown_test"),
            status=TestStatus(status),
            ci_system=CISystem.github_actions,
        ))
        return events