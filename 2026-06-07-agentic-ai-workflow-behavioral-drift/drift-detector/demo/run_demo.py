"""
Demo Script — Simulates agentic workflow drift detection end-to-end.

Scenario:
  Phase 1 (runs 1-5): Stable baseline runs — customer service agent working correctly
  Phase 2 (run 6):    Mark first 5 runs as baselines
  Phase 3 (runs 7-12): Drifted runs — agent starts using different tools,
                        reasoning changes, confidence drops
  Phase 4: Show drift detection kicking in

Run: python demo/run_demo.py
"""

import asyncio
import random
import time
import sys
import os
import httpx
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

API_URL = "http://localhost:8000"
WORKFLOW_ID = "customer-service-agent-v1"

# Baseline behavior: agent uses these tools in this order
BASELINE_TOOLS = ["knowledge_base_search", "customer_lookup", "response_generator"]
BASELINE_STEPS = ["classify_intent", "retrieve_context", "generate_response"]
BASELINE_REASONING = [
    "Classifying customer intent based on query keywords and sentiment analysis",
    "Retrieving relevant knowledge base articles for the identified intent category",
    "Generating personalized response using retrieved context and customer history",
]
BASELINE_CONFIDENCE = (0.82, 0.91)  # Typical confidence range

# Drifted behavior: agent switches tools, reasoning changes, confidence drops
DRIFTED_TOOLS = ["web_search", "generic_llm_call", "response_generator", "escalation_checker"]
DRIFTED_STEPS = ["web_search_query", "parse_web_results", "generate_response", "check_escalation"]
DRIFTED_REASONING = [
    "Performing web search to find general information about the customer query topic",
    "Parsing web search results to extract relevant passages for the customer question",
    "Generating response from web content rather than knowledge base — less accurate",
    "Checking if this response needs escalation due to low confidence in web-sourced answer",
]
DRIFTED_CONFIDENCE = (0.45, 0.62)


async def register_workflow(client: httpx.AsyncClient):
    """Register the demo workflow."""
    resp = await client.post(
        f"{API_URL}/api/workflows",
        json={
            "workflow_id": WORKFLOW_ID,
            "name": "Customer Service Agent v1",
            "description": "Handles customer support queries using knowledge base retrieval",
            "expected_steps": BASELINE_STEPS,
            "expected_tools": BASELINE_TOOLS,
        },
    )
    if resp.status_code in (201, 409):
        print(f"✓ Workflow registered: {WORKFLOW_ID}")
    else:
        print(f"⚠ Workflow registration: {resp.status_code} {resp.text}")


def build_trace(
    workflow_id: str,
    tools: list,
    steps: list,
    reasonings: list,
    confidence_range: tuple,
    is_noisy: bool = False,
) -> dict:
    """Build a synthetic trace payload."""
    run_id = str(uuid.uuid4())
    start_time = time.time()
    spans = []

    for i, (step, tool, reasoning) in enumerate(zip(steps, tools, reasonings)):
        confidence = random.uniform(*confidence_range)
        if is_noisy:
            confidence += random.gauss(0, 0.05)
            confidence = max(0.1, min(0.99, confidence))

        span_start = start_time + i * 0.3
        span = {
            "span_id": str(uuid.uuid4()),
            "trace_id": run_id,
            "workflow_id": workflow_id,
            "step_name": step,
            "step_index": i,
            "tool_name": tool,
            "reasoning": reasoning,
            "output": f"[Output of {step}: processed successfully]",
            "confidence": confidence,
            "retrieved_chunk_hashes": [f"chunk_{random.randint(100,999)}" for _ in range(2)],
            "token_count": random.randint(150, 400),
            "latency_ms": random.uniform(200, 800),
            "start_time": span_start,
            "end_time": span_start + random.uniform(0.1, 0.5),
            "attributes": {"model": "gpt-4o", "temperature": 0.7},
            "reasoning_embedding": None,  # SDK would fill this — demo uses None
        }
        spans.append(span)

    avg_confidence = sum(s["confidence"] for s in spans) / len(spans)

    return {
        "run_id": run_id,
        "workflow_id": workflow_id,
        "start_time": start_time,
        "end_time": start_time + len(spans) * 0.4,
        "span_count": len(spans),
        "spans": spans,
        "metadata": {},
        "tool_sequence": [s["tool_name"] for s in spans],
        "step_sequence": [s["step_name"] for s in spans],
        "avg_confidence": avg_confidence,
    }


async def ingest_trace(client: httpx.AsyncClient, trace: dict) -> str:
    """POST a trace to the API."""
    resp = await client.post(f"{API_URL}/api/traces", json=trace)
    if resp.status_code in (200, 201):
        return trace["run_id"]
    else:
        print(f"  ⚠ Ingest failed: {resp.status_code} {resp.text[:200]}")
        return trace["run_id"]


async def promote_baseline(
    client: httpx.AsyncClient, workflow_id: str, run_id: str
):
    """Promote a run to baseline."""
    resp = await client.post(
        f"{API_URL}/api/baselines/{workflow_id}",
        json={"run_id": run_id, "notes": "Golden run from demo"},
    )
    if resp.status_code == 200:
        return True
    print(f"  ⚠ Baseline promotion failed: {resp.status_code}")
    return False


async def wait_for_drift_scores(
    client: httpx.AsyncClient, workflow_id: str, min_count: int, timeout: int = 60
):
    """Wait until at least min_count drift scores are computed."""
    print(f"  ⏳ Waiting for drift worker to process {min_count} runs...")
    start = time.time()
    while time.time() - start < timeout:
        resp = await client.get(f"{API_URL}/api/drift/{workflow_id}?limit=100")
        if resp.status_code == 200:
            data = resp.json()
            count = len(data.get("scores", []))
            if count >= min_count:
                return data
        await asyncio.sleep(2)
    print(f"  ⚠ Timeout waiting for drift scores")
    return None


async def print_drift_summary(client: httpx.AsyncClient, workflow_id: str):
    """Print current drift scores."""
    resp = await client.get(f"{API_URL}/api/drift/{workflow_id}?limit=100")
    if resp.status_code != 200:
        return
    data = resp.json()
    scores = data.get("scores", [])
    print(f"\n{'─'*70}")
    print(f"  Drift Timeline for: {workflow_id}")
    print(f"  Baselines: {data.get('baseline_count', 0)}")
    print(f"{'─'*70}")
    print(f"  {'Run':<10} {'Composite':<12} {'Structural':<12} {'Semantic':<12} {'Distrib.':<12} {'Level'}")
    print(f"{'─'*70}")
    for i, s in enumerate(scores):
        level_icon = {"normal": "✅", "warning": "⚠️ ", "alert": "🚨"}.get(
            s["alert_level"], "  "
        )
        print(
            f"  Run {i+1:<6} "
            f"{s['composite_score']:.3f}       "
            f"{s['structural_score']:.3f}       "
            f"{s['semantic_score']:.3f}       "
            f"{s['distributional_score']:.3f}       "
            f"{level_icon} {s['alert_level']}"
        )
    print(f"{'─'*70}")


async def print_alerts(client: httpx.AsyncClient, workflow_id: str):
    """Print active alerts."""
    resp = await client.get(f"{API_URL}/api/alerts?workflow_id={workflow_id}")
    if resp.status_code != 200:
        return
    alerts = resp.json()
    if not alerts:
        print("\n  No alerts generated.")
        return

    print(f"\n{'═'*70}")
    print(f"  🚨 ALERTS ({len(alerts)} total)")
    print(f"{'═'*70}")
    for alert in alerts:
        print(f"\n  Level: {alert['alert_level'].upper()}")
        print(f"  Composite Score: {alert['composite_score']:.3f}")
        print(f"  Run: {alert['run_id'][:16]}...")
        if alert.get("explanation"):
            print(f"\n  Explanation:")
            for line in alert["explanation"].split("\n"):
                print(f"    {line}")
    print(f"{'═'*70}\n")


async def main():
    print("\n" + "═" * 70)
    print("  🔍 Behavioral Drift Detection Demo")
    print("  Simulating customer service agent workflow drift")
    print("═" * 70 + "\n")

    async with httpx.AsyncClient(timeout=30.0) as client:

        # Verify API is up
        try:
            resp = await client.get(f"{API_URL}/health")
            resp.raise_for_status()
            print(f"✓ API is running at {API_URL}\n")
        except Exception as e:
            print(f"✗ Cannot reach API at {API_URL}: {e}")
            print("  Make sure the API is running: uvicorn backend.api.main:app --port 8000")
            sys.exit(1)

        # Register workflow
        await register_workflow(client)

        # ── Phase 1: Baseline runs ─────────────────────────────────────────────
        print("\n📋 Phase 1: Ingesting 5 baseline (golden) runs...")
        baseline_run_ids = []

        for i in range(5):
            trace = build_trace(
                workflow_id=WORKFLOW_ID,
                tools=BASELINE_TOOLS,
                steps=BASELINE_STEPS,
                reasonings=BASELINE_REASONING,
                confidence_range=BASELINE_CONFIDENCE,
                is_noisy=True,
            )
            run_id = await ingest_trace(client, trace)
            baseline_run_ids.append(run_id)
            print(f"  Ingested baseline run {i+1}: {run_id[:16]}...")
            await asyncio.sleep(0.2)

        # ── Phase 2: Promote baselines ─────────────────────────────────────────
        print("\n📌 Phase 2: Promoting runs to golden baselines...")
        for run_id in baseline_run_ids:
            success = await promote_baseline(client, WORKFLOW_ID, run_id)
            if success:
                print(f"  ✓ Promoted: {run_id[:16]}...")

        # ── Phase 3: Normal runs (should show low drift) ───────────────────────
        print("\n🟢 Phase 3: Ingesting 5 normal (non-drifted) runs...")
        normal_run_ids = []

        for i in range(5):
            trace = build_trace(
                workflow_id=WORKFLOW_ID,
                tools=BASELINE_TOOLS,
                steps=BASELINE_STEPS,
                reasonings=BASELINE_REASONING,
                confidence_range=BASELINE_CONFIDENCE,
                is_noisy=True,
            )
            run_id = await ingest_trace(client, trace)
            normal_run_ids.append(run_id)
            print(f"  Ingested normal run {i+1}: {run_id[:16]}...")
            await asyncio.sleep(0.2)

        # Wait for drift worker to process normal runs
        print("\n  Waiting for drift detection worker...")
        await asyncio.sleep(8)

        # ── Phase 4: Drifted runs ──────────────────────────────────────────────
        print("\n🔴 Phase 4: Injecting 6 DRIFTED runs (agent switched tools)...")
        drifted_run_ids = []

        for i in range(6):
            # Progressively increase drift
            if i < 2:
                # Subtle drift — mixed tools
                tools = ["knowledge_base_search", "web_search", "response_generator"]
                steps = BASELINE_STEPS
                reasonings = BASELINE_REASONING
                conf_range = (0.70, 0.80)
            else:
                # Full drift
                tools = DRIFTED_TOOLS
                steps = DRIFTED_STEPS
                reasonings = DRIFTED_REASONING
                conf_range = DRIFTED_CONFIDENCE

            trace = build_trace(
                workflow_id=WORKFLOW_ID,
                tools=tools,
                steps=steps,
                reasonings=reasonings,
                confidence_range=conf_range,
                is_noisy=True,
            )
            run_id = await ingest_trace(client, trace)
            drifted_run_ids.append(run_id)
            print(f"  Ingested drifted run {i+1}: {run_id[:16]}... (confidence: {conf_range})")
            await asyncio.sleep(0.3)

        # ── Wait for processing ────────────────────────────────────────────────
        print("\n  ⏳ Waiting for drift worker to process all runs...")
        total_expected = len(normal_run_ids) + len(drifted_run_ids)
        await wait_for_drift_scores(client, WORKFLOW_ID, total_expected, timeout=90)

        # ── Show results ───────────────────────────────────────────────────────
        await print_drift_summary(client, WORKFLOW_ID)
        await print_alerts(client, WORKFLOW_ID)

        # Summary
        resp = await client.get(f"{API_URL}/api/summary")
        if resp.status_code == 200:
            summary = resp.json()
            print(f"\n📊 Platform Summary:")
            print(f"  Workflows monitored: {summary['workflow_count']}")
            print(f"  Total traces ingested: {summary['trace_count']}")
            print(f"  Active alerts: {summary['active_alerts']}")
            print(f"  Baseline runs: {summary['baseline_count']}")

        print(f"\n✅ Demo complete! Open http://localhost:3000 for the dashboard.\n")


if __name__ == "__main__":
    asyncio.run(main())