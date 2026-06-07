"""
Agent Simulation Example

Demonstrates the full end-to-end flow:
1. Register a workflow
2. Submit "golden run" traces (normal behavior)
3. Approve baselines
4. Submit traces with injected drift (wrong tools, low confidence)
5. Watch drift scores accumulate

Run with: python -m examples.simulate_agent
"""

from __future__ import annotations

import asyncio
import random
import time
import uuid
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)

API_BASE = "http://localhost:8000"


async def register_workflow(client: httpx.AsyncClient, name: str, expected_tools: list[str]) -> str:
    """Register a workflow and return its ID."""
    response = await client.post(
        f"{API_BASE}/api/v1/workflows",
        json={
            "name": name,
            "description": f"Simulated workflow: {name}",
            "expected_tools": expected_tools,
        },
    )
    response.raise_for_status()
    workflow_id = response.json()["id"]
    logger.info("workflow_registered", name=name, workflow_id=workflow_id)
    return workflow_id


def make_trace(
    workflow_id: str,
    tool_sequence: list[str],
    confidences: list[float],
    outputs: list[str],
) -> dict:
    """Build a trace payload matching the SDK output format."""
    run_id = str(uuid.uuid4())
    start = time.time() - random.uniform(0.5, 3.0)
    end = start + random.uniform(1.0, 5.0)
    
    steps = []
    for i, (tool, conf, output) in enumerate(zip(tool_sequence, confidences, outputs)):
        step_start = start + i * 0.5
        steps.append({
            "span_id": str(uuid.uuid4()),
            "run_id": run_id,
            "workflow_id": workflow_id,
            "step_index": i,
            "tool_name": tool,
            "start_time": step_start,
            "end_time": step_start + 0.3,
            "duration_ms": 300,
            "output_text": output,
            "confidence": conf,
            "retrieved_chunks": [],
            "metadata": {},
            "error": None,
        })
    
    return {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "start_time": start,
        "end_time": end,
        "duration_ms": (end - start) * 1000,
        "steps": steps,
        "metadata": {"simulated": True},
        "error": None,
        "tool_sequence": tool_sequence,
        "step_count": len(steps),
    }


async def submit_trace(client: httpx.AsyncClient, trace: dict) -> dict:
    response = await client.post(f"{API_BASE}/api/v1/traces", json=trace)
    response.raise_for_status()
    return response.json()


async def approve_baseline(
    client: httpx.AsyncClient,
    workflow_id: str,
    run_id: str,
    approved_by: str = "simulation-script",
) -> dict:
    response = await client.post(
        f"{API_BASE}/api/v1/baselines/{workflow_id}",
        json={"run_id": run_id, "approved_by": approved_by, "notes": "Simulated golden run"},
    )
    response.raise_for_status()
    return response.json()


async def wait_for_processing(client: httpx.AsyncClient, run_id: str, max_wait: int = 30):
    """Poll until a trace is processed or timeout."""
    for _ in range(max_wait):
        await asyncio.sleep(1)
        resp = await client.get(f"{API_BASE}/api/v1/traces/{run_id}")
        if resp.status_code == 200:
            data = resp.json()
            if data.get("processed"):
                return data
    return None


async def main():
    # ── Scenario: Customer Service Agent ──────────────────────────────────────
    # Normal flow: search → retrieve → classify → respond
    # Drift: skips retrieve, uses wrong tools, confidence drops
    
    NORMAL_TOOLS = ["search", "retrieve", "classify", "respond"]
    NORMAL_CONFIDENCES = [0.91, 0.87, 0.93, 0.89]
    NORMAL_OUTPUTS = [
        "Found 5 relevant articles about the customer's billing issue",
        "Retrieved 3 policy documents relevant to disputed charges",
        "Classified as: billing_dispute, priority: medium",
        "Drafted response explaining the dispute resolution process to the customer",
    ]

    # Drifted flow: different tools, lower confidence, divergent outputs
    DRIFTED_TOOLS = ["web_search", "summarize", "respond"]
    DRIFTED_CONFIDENCES = [0.52, 0.48, 0.45]
    DRIFTED_OUTPUTS = [
        "Generic web results about billing, not specific to our policies",
        "Summarized general information about refunds",
        "Sent a vague response that did not address the specific dispute",
    ]

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check API is up
        try:
            health = await client.get(f"{API_BASE}/health")
            health.raise_for_status()
            print(f"✓ API is up: {health.json()}")
        except Exception as exc:
            print(f"✗ API not reachable at {API_BASE}: {exc}")
            print("  Start the API with: uvicorn api.main:app --reload --port 8000")
            return

        # Register workflow
        workflow_id = await register_workflow(
            client,
            name="Customer Service Agent",
            expected_tools=NORMAL_TOOLS,
        )
        print(f"✓ Workflow registered: {workflow_id}")

        # ── Phase 1: Submit golden runs ────────────────────────────────────
        print("\n── Phase 1: Submitting golden runs ──")
        golden_run_ids = []
        for i in range(3):
            # Add slight variation to golden runs (agents are non-deterministic)
            tools = NORMAL_TOOLS.copy()
            confs = [c + random.uniform(-0.03, 0.03) for c in NORMAL_CONFIDENCES]
            
            trace = make_trace(workflow_id, tools, confs, NORMAL_OUTPUTS)
            result = await submit_trace(client, trace)
            golden_run_ids.append(trace["run_id"])
            print(f"  Submitted golden run {i+1}: {trace['run_id'][:8]}... → {result['status']}")

        # Wait for worker to process
        print("\n  Waiting for worker to process traces...")
        await asyncio.sleep(5)

        # Approve as baselines
        print("\n── Phase 2: Approving baselines ──")
        for run_id in golden_run_ids:
            try:
                result = await approve_baseline(client, workflow_id, run_id)
                print(f"  Baseline approved: {run_id[:8]}...")
            except Exception as exc:
                print(f"  Could not approve {run_id[:8]}...: {exc}")

        # ── Phase 3: Submit normal runs (should show low drift) ────────────
        print("\n── Phase 3: Normal production runs ──")
        for i in range(4):
            confs = [c + random.uniform(-0.05, 0.05) for c in NORMAL_CONFIDENCES]
            trace = make_trace(workflow_id, NORMAL_TOOLS, confs, NORMAL_OUTPUTS)
            result = await submit_trace(client, trace)
            print(f"  Normal run {i+1}: {trace['run_id'][:8]}...")
            await asyncio.sleep(0.5)

        print("\n  Waiting for drift detection...")
        await asyncio.sleep(8)

        # Check drift scores
        resp = await client.get(
            f"{API_BASE}/api/v1/drift/timeseries/{workflow_id}",
            params={"hours": 1},
        )
        if resp.status_code == 200:
            scores = resp.json()
            print(f"\n  Drift scores for normal runs:")
            for s in scores:
                print(
                    f"    {s['run_id'][:8]}... composite={s['composite_score']:.3f} "
                    f"severity={s['severity']} alert={s['alert_triggered']}"
                )

        # ── Phase 4: Inject drift ──────────────────────────────────────────
        print("\n── Phase 4: Injecting behavioral drift ──")
        drifted_run_ids = []
        for i in range(6):
            # Progressively worsen the drift
            noise = i * 0.05
            confs = [max(c - noise, 0.1) for c in DRIFTED_CONFIDENCES]
            
            trace = make_trace(workflow_id, DRIFTED_TOOLS, confs, DRIFTED_OUTPUTS)
            result = await submit_trace(client, trace)
            drifted_run_ids.append(trace["run_id"])
            print(f"  Drifted run {i+1}: {trace['run_id'][:8]}... (conf={confs[0]:.2f})")
            await asyncio.sleep(0.3)

        print("\n  Waiting for drift detection...")
        await asyncio.sleep(12)

        # Check drift scores for drifted runs
        resp = await client.get(
            f"{API_BASE}/api/v1/drift/timeseries/{workflow_id}",
            params={"hours": 1},
        )
        if resp.status_code == 200:
            scores = resp.json()
            print(f"\n  All drift scores (chronological):")
            print(f"  {'run_id':10} {'composite':10} {'struct':8} {'semantic':9} {'distrib':9} {'severity':10} {'alert'}")
            print(f"  {'-'*75}")
            for s in scores[-13:]:  # Last 13 runs
                print(
                    f"  {s['run_id'][:8]}... "
                    f"{s.get('composite_score', 0):.3f}      "
                    f"{s.get('structural_score', 0) or 0:.3f}    "
                    f"{s.get('semantic_score', 0) or 0:.3f}     "
                    f"{s.get('distributional_score', 0) or 0:.3f}     "
                    f"{s.get('severity', 'N/A'):10} "
                    f"{'🚨' if s.get('alert_triggered') else '✓'}"
                )

        # ── Phase 5: Workflow Summary ──────────────────────────────────────
        print("\n── Phase 5: Workflow health summary ──")
        resp = await client.get(f"{API_BASE}/api/v1/workflows/{workflow_id}/summary")
        if resp.status_code == 200:
            summary = resp.json()
            print(f"  Workflow: {summary['workflow_name']}")
            print(f"  Recent composite score: {summary.get('recent_composite_score', 'N/A')}")
            print(f"  Trend: {summary['trend']}")
            print(f"  Alerts (24h): {summary['alert_count_24h']}")
            print(f"  Baselines approved: {summary['baseline_count']}")

        # Check latest alerts
        resp = await client.get(f"{API_BASE}/api/v1/drift/alerts/{workflow_id}")
        if resp.status_code == 200:
            alerts = resp.json()
            print(f"\n── Recent alerts: {len(alerts)} ──")
            for alert in alerts[:3]:
                print(f"  [{alert['severity'].upper()}] run={alert['run_id'][:8]}... "
                      f"score={alert['composite_score']:.3f}")
                if alert.get("explanation"):
                    print(f"  LLM explanation: {alert['explanation'][:200]}...")

        print(f"\n✓ Simulation complete. Dashboard: http://localhost:5173/?workflow={workflow_id}")
        print(f"  API docs: http://localhost:8000/docs")


if __name__ == "__main__":
    asyncio.run(main())