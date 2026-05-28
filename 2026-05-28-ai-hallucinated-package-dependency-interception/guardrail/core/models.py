"""Data models for GuardRail validation results."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Any
import time


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_score(cls, score: float) -> "RiskLevel":
        if score < 0.3:
            return cls.LOW
        elif score < 0.6:
            return cls.MEDIUM
        elif score < 0.8:
            return cls.HIGH
        else:
            return cls.CRITICAL


class Ecosystem(str, Enum):
    PYPI = "pypi"
    NPM = "npm"
    CARGO = "cargo"
    GO = "go"
    MAVEN = "maven"

    @classmethod
    def from_manifest(cls, filename: str) -> Optional["Ecosystem"]:
        mapping = {
            "requirements.txt": cls.PYPI,
            "setup.py": cls.PYPI,
            "setup.cfg": cls.PYPI,
            "pyproject.toml": cls.PYPI,
            "Pipfile": cls.PYPI,
            "package.json": cls.NPM,
            "package-lock.json": cls.NPM,
            "yarn.lock": cls.NPM,
            "Cargo.toml": cls.CARGO,
            "Cargo.lock": cls.CARGO,
            "go.mod": cls.GO,
            "pom.xml": cls.MAVEN,
        }
        import os
        basename = os.path.basename(filename)
        return mapping.get(basename)


@dataclass
class RegistryResult:
    exists: bool
    ecosystem: str
    package_name: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HeuristicResult:
    score: float  # 0.0 = no flags, 1.0 = maximum suspicion
    flags: List[str] = field(default_factory=list)
    similar_packages: List[str] = field(default_factory=list)
    edit_distance: Optional[int] = None
    ai_pattern_score: float = 0.0


@dataclass
class ReputationResult:
    score: float  # 0.0 = great reputation, 1.0 = poor/unknown
    download_count: Optional[int] = None
    days_since_publish: Optional[int] = None
    maintainer_count: Optional[int] = None
    has_github: bool = False
    flags: List[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    package_name: str
    ecosystem: str
    risk_score: float
    risk_level: RiskLevel
    exists_on_registry: bool
    registry_result: Optional[RegistryResult] = None
    heuristic_result: Optional[HeuristicResult] = None
    reputation_result: Optional[ReputationResult] = None
    policy_override: Optional[str] = None  # "allow" | "block"
    flags: List[str] = field(default_factory=list)
    remediation: Optional[str] = None
    cached: bool = False
    check_duration_ms: float = 0.0

    @property
    def should_block(self) -> bool:
        if self.policy_override == "allow":
            return False
        if self.policy_override == "block":
            return True
        return self.risk_level in (RiskLevel.CRITICAL,)

    @property
    def should_warn(self) -> bool:
        if self.policy_override == "allow":
            return False
        return self.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "package_name": self.package_name,
            "ecosystem": self.ecosystem,
            "risk_score": round(self.risk_score, 3),
            "risk_level": self.risk_level.value,
            "exists_on_registry": self.exists_on_registry,
            "flags": self.flags,
            "remediation": self.remediation,
            "policy_override": self.policy_override,
            "cached": self.cached,
            "check_duration_ms": round(self.check_duration_ms, 1),
            "registry": {
                "exists": self.registry_result.exists if self.registry_result else False,
                "error": self.registry_result.error if self.registry_result else None,
                "metadata": self.registry_result.metadata if self.registry_result else {},
            } if self.registry_result else None,
            "heuristics": {
                "score": round(self.heuristic_result.score, 3),
                "flags": self.heuristic_result.flags,
                "similar_packages": self.heuristic_result.similar_packages,
                "edit_distance": self.heuristic_result.edit_distance,
                "ai_pattern_score": round(self.heuristic_result.ai_pattern_score, 3),
            } if self.heuristic_result else None,
            "reputation": {
                "score": round(self.reputation_result.score, 3),
                "download_count": self.reputation_result.download_count,
                "days_since_publish": self.reputation_result.days_since_publish,
                "maintainer_count": self.reputation_result.maintainer_count,
                "has_github": self.reputation_result.has_github,
                "flags": self.reputation_result.flags,
            } if self.reputation_result else None,
        }


@dataclass
class ScanReport:
    manifest_path: str
    ecosystem: str
    total_packages: int
    results: List[ValidationResult]
    scan_duration_ms: float
    timestamp: float = field(default_factory=time.time)
    policy_server_used: bool = False

    @property
    def blocked_count(self) -> int:
        return sum(1 for r in self.results if r.should_block)

    @property
    def warned_count(self) -> int:
        return sum(1 for r in self.results if r.should_warn)

    @property
    def clean_count(self) -> int:
        return sum(1 for r in self.results if r.risk_level == RiskLevel.LOW)

    @property
    def not_found_count(self) -> int:
        return sum(1 for r in self.results if not r.exists_on_registry)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_path": self.manifest_path,
            "ecosystem": self.ecosystem,
            "summary": {
                "total": self.total_packages,
                "blocked": self.blocked_count,
                "warned": self.warned_count,
                "clean": self.clean_count,
                "not_found": self.not_found_count,
            },
            "scan_duration_ms": round(self.scan_duration_ms, 1),
            "timestamp": self.timestamp,
            "policy_server_used": self.policy_server_used,
            "results": [r.to_dict() for r in self.results],
        }