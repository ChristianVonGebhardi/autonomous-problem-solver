"""
Main Validation Engine Orchestrator.

Runs registry, heuristic, and reputation checks in parallel,
combining results into a final risk score.
"""
from __future__ import annotations
import asyncio
import logging
import time
from typing import List, Optional, Dict, Any

import httpx

from .cache import Cache
from .heuristics import HeuristicEngine
from .models import Ecosystem, RiskLevel, ValidationResult, ScanReport
from .registry import RegistryChecker
from .reputation import ReputationScorer
from .policy import PolicyClient

logger = logging.getLogger(__name__)


class Validator:
    """
    Orchestrates all validation checks for a package.
    
    Checks run in parallel:
    1. Registry existence (weight: 0.40)
    2. Heuristic analysis (weight: 0.30)
    3. Reputation scoring (weight: 0.30)
    """

    # Weight of each check in final risk score
    REGISTRY_WEIGHT = 0.40
    HEURISTIC_WEIGHT = 0.30
    REPUTATION_WEIGHT = 0.30

    def __init__(
        self,
        cache: Optional[Cache] = None,
        policy_client: Optional[PolicyClient] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        self.cache = cache or Cache()
        self._http_client = http_client
        self._owns_http = http_client is None
        self.registry_checker = RegistryChecker(self.cache, http_client)
        self.heuristic_engine = HeuristicEngine()
        self.reputation_scorer = ReputationScorer(self.cache, http_client)
        self.policy_client = policy_client

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                headers={"User-Agent": "guardrail-scanner/0.1.0"},
                follow_redirects=True,
            )
            # Share the client with sub-components
            self.registry_checker._client = self._http_client
            self.registry_checker._owns_client = False
            self.reputation_scorer._client = self._http_client
            self.reputation_scorer._owns_client = False
        return self._http_client

    async def close(self):
        await self.cache.close()
        if self._owns_http and self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def validate(
        self,
        package_name: str,
        ecosystem: Ecosystem,
    ) -> ValidationResult:
        """Validate a single package. Runs all checks in parallel."""
        start_time = time.monotonic()
        await self._get_http_client()
        
        # Check policy first (allow/block list)
        policy_override = None
        if self.policy_client:
            policy_override = await self.policy_client.check(package_name, ecosystem.value)
            if policy_override == "allow":
                duration_ms = (time.monotonic() - start_time) * 1000
                return ValidationResult(
                    package_name=package_name,
                    ecosystem=ecosystem.value,
                    risk_score=0.0,
                    risk_level=RiskLevel.LOW,
                    exists_on_registry=True,
                    policy_override="allow",
                    flags=["policy:allowlisted"],
                    check_duration_ms=duration_ms,
                )
            elif policy_override == "block":
                duration_ms = (time.monotonic() - start_time) * 1000
                return ValidationResult(
                    package_name=package_name,
                    ecosystem=ecosystem.value,
                    risk_score=1.0,
                    risk_level=RiskLevel.CRITICAL,
                    exists_on_registry=False,
                    policy_override="block",
                    flags=["policy:blocklisted"],
                    remediation=f"Package '{package_name}' is on the block list. Contact your security team.",
                    check_duration_ms=duration_ms,
                )

        # Run all checks in parallel
        registry_task = asyncio.create_task(
            self.registry_checker.check(package_name, ecosystem)
        )
        heuristic_task = asyncio.create_task(
            asyncio.get_event_loop().run_in_executor(
                None,
                self.heuristic_engine.analyze,
                package_name,
                ecosystem.value,
            )
        )

        registry_result = await registry_task
        heuristic_result = await heuristic_task

        # Reputation check runs after registry (uses registry metadata)
        reputation_result = await self.reputation_scorer.score(
            package_name, ecosystem, registry_result
        )

        # Calculate combined risk score
        registry_score = 0.0 if registry_result.exists else 1.0
        if registry_result.error and not registry_result.exists:
            # Couldn't reach registry: treat as uncertain (medium risk from registry check)
            registry_score = 0.5

        combined_score = (
            registry_score * self.REGISTRY_WEIGHT +
            heuristic_result.score * self.HEURISTIC_WEIGHT +
            reputation_result.score * self.REPUTATION_WEIGHT
        )
        combined_score = min(combined_score, 1.0)

        risk_level = RiskLevel.from_score(combined_score)

        # Collect all flags
        flags = []
        if not registry_result.exists:
            if registry_result.error:
                flags.append(f"registry-check-failed:{registry_result.error}")
            else:
                flags.append("package-not-found-on-registry")
        flags.extend(heuristic_result.flags)
        flags.extend(reputation_result.flags)

        # Generate remediation hint
        remediation = self._generate_remediation(
            package_name, ecosystem, registry_result, heuristic_result, reputation_result
        )

        duration_ms = (time.monotonic() - start_time) * 1000

        return ValidationResult(
            package_name=package_name,
            ecosystem=ecosystem.value,
            risk_score=combined_score,
            risk_level=risk_level,
            exists_on_registry=registry_result.exists,
            registry_result=registry_result,
            heuristic_result=heuristic_result,
            reputation_result=reputation_result,
            policy_override=policy_override,
            flags=flags,
            remediation=remediation,
            check_duration_ms=duration_ms,
        )

    def _generate_remediation(
        self,
        package_name: str,
        ecosystem: Ecosystem,
        registry_result,
        heuristic_result,
        reputation_result,
    ) -> Optional[str]:
        """Generate a human-readable remediation hint."""
        hints = []

        if not registry_result.exists:
            hints.append(
                f"Package '{package_name}' does not exist on {ecosystem.value} registry. "
                f"It may be hallucinated by an AI assistant."
            )

        if heuristic_result.similar_packages:
            similar = heuristic_result.similar_packages[:3]
            if registry_result.exists:
                hints.append(
                    f"WARNING: '{package_name}' is very similar to known packages: {', '.join(similar)}. "
                    f"This could be a typosquat attack."
                )
            else:
                hints.append(
                    f"Did you mean one of: {', '.join(similar)}? "
                    f"These are known legitimate packages."
                )

        if reputation_result.flags:
            rep_flags = [f for f in reputation_result.flags if "recently" in f or "week" in f or "no-downloads" in f.lower() or "almost" in f]
            if rep_flags:
                hints.append(
                    f"Reputation concerns: {', '.join(rep_flags[:3])}. "
                    f"Verify this package is legitimate before installing."
                )

        return " | ".join(hints) if hints else None

    async def validate_many(
        self,
        packages: List[tuple],  # [(name, ecosystem), ...]
        concurrency: int = 10,
    ) -> List[ValidationResult]:
        """Validate multiple packages with controlled concurrency."""
        await self._get_http_client()
        semaphore = asyncio.Semaphore(concurrency)

        async def _bounded_validate(name: str, eco: Ecosystem) -> ValidationResult:
            async with semaphore:
                return await self.validate(name, eco)

        tasks = [_bounded_validate(name, eco) for name, eco in packages]
        return await asyncio.gather(*tasks, return_exceptions=False)

    async def scan_manifest(
        self,
        manifest_path: str,
        ecosystem: Optional[Ecosystem] = None,
    ) -> ScanReport:
        """Parse a manifest file and validate all dependencies."""
        from .parsers import parse_manifest
        import time as time_module

        start = time_module.time()

        if ecosystem is None:
            ecosystem = Ecosystem.from_manifest(manifest_path)
            if ecosystem is None:
                raise ValueError(f"Cannot determine ecosystem from manifest: {manifest_path}")

        packages = parse_manifest(manifest_path, ecosystem)
        
        results = await self.validate_many(
            [(name, ecosystem) for name in packages],
        )

        elapsed_ms = (time_module.time() - start) * 1000

        return ScanReport(
            manifest_path=manifest_path,
            ecosystem=ecosystem.value,
            total_packages=len(packages),
            results=results,
            scan_duration_ms=elapsed_ms,
            policy_server_used=self.policy_client is not None,
        )

    async def __aenter__(self):
        await self._get_http_client()
        return self

    async def __aexit__(self, *args):
        await self.close()