"""
ATCAP Demo — simulates multiple AI agents making LLM calls with business context.

Run: python -m demo.run_demo
"""
import asyncio
import random
import uuid
from datetime import datetime, timedelta
import httpx

COLLECTOR_URL = "http://localhost:8000"

TEAMS = ["platform", "search", "recommendations", "data-infra", "frontend"]

FEATURES = {
    "platform": ["code-review-agent", "incident-responder", "deploy-assistant"],
    "search": ["ai-search", "query-expansion", "result-reranking"],
    "recommendations": ["product-rec-engine", "personalization", "a-b-tester"],
    "data-infra": ["schema-analyzer", "query-optimizer", "anomaly-detector"],
    "frontend": ["ux-copilot", "a11y-checker", "component-generator"],
}

MODELS = [
    ("openai", "gpt-4o"),
    ("openai", "gpt-4o-mini"),
    ("openai", "gpt-3.5-turbo"),
    ("anthropic", "claude-3-5-sonnet-20241022"),
    ("anthropic", "claude-3-haiku-20240307"),
    ("google", "gemini-1.5-flash"),
]

ENTITY_TYPES = [
    ("ticket", "JIRA-{n}"),
    ("pr", "PR-{n}"),
    ("pipeline", "pipe-{n}"),
]


def make_event(days_back: float = 0) -> dict:
    team = random.choice(TEAMS)
    feature = random.choice(FEATURES[team])
    provider, model = random.choice(MODELS)

    entity_type, entity_tmpl = random.choice(ENTITY_TYPES)
    entity_id = entity_tmpl.format(n=random.randint(100, 9999))

    # Heavier models use more tokens
    base_prompt = random.randint(200, 4000)
    base_completion = random.randint(100, 2000)

    # Some workflows are 10x more expensive (agentic loops)
    if random.random() < 0.15:
        base_prompt *= random.randint(5, 15)
        base_completion *= random.randint(5, 10)

    ts = datetime.utcnow() - timedelta(days=days_back, seconds=random.randint(0, 86400))

    return {
        "trace_id": str(uuid.uuid4()),
        "span_id": str(uuid.uuid4()),
        "team": team,
        "feature": feature,
        "workflow_id": f"wf-{team}-{feature}-{random.randint(1000,9999)}",
        "agent_run_id": f"run-{uuid.uuid4().hex[:8]}",
        "business_entity_id": entity_id,
        "business_entity_type": entity_type,
        "provider": provider,
        "model": model,
        "prompt_tokens": base_prompt,
        "completion_tokens": base_completion,
        "latency_ms": random.randint(200, 8000),
        "timestamp": ts.isoformat(),
    }


def make_value_event(days_back: float = 0) -> dict:
    team = random.choice(TEAMS)
    feature = random.choice(FEATURES[team])

    event_types = [
        ("github", "pr_merged", 2.0, 150.0),
        ("jira", "ticket_closed", 1.0, 50.0),
        ("jira", "bug_fixed", 1.5, 100.0),
        ("github", "deployment", 3.0, 300.0),
        ("webhook", "feature_shipped", 5.0, 500.0),
    ]
    source, event_type, value_pts, value_usd_base = random.choice(event_types)
    value_usd = value_usd_base * random.uniform(0.5, 2.0) if random.random() > 0.3 else None

    ts = datetime.utcnow() - timedelta(days=days_back, seconds=random.randint(0, 86400))

    return {
        "source": source,
        "event_type": event_type,
        "team": team,
        "feature": feature,
        "business_entity_id": f"{event_type.upper()}-{random.randint(100, 9999)}",
        "value_points": value_pts,
        "value_usd": round(value_usd, 2) if value_usd else None,
        "title": f"{event_type.replace('_', ' ').title()} by {team} team",
        "url": f"https://github.com/example/repo/pull/{random.randint(100, 500)}",
    }


async def seed_historical_data(client: httpx.AsyncClient, days: int = 30):
    """Seed realistic historical data spread over the past N days."""
    print(f"📦 Seeding {days} days of historical token events...")

    batch = []
    total_events = 0
    for day_back in range(days, 0, -1):
        # Simulate varying daily volume
        daily_calls = random.randint(50, 200)
        for _ in range(daily_calls):
            batch.append(make_event(days_back=day_back))
            if len(batch) >= 50:
                resp = await client.post(
                    f"{COLLECTOR_URL}/api/v1/events/batch",
                    json={"events": batch},
                    timeout=30.0,
                )
                total_events += len(batch)
                batch = []

    if batch:
        await client.post(
            f"{COLLECTOR_URL}/api/v1/events/batch",
            json={"events": batch},
            timeout=30.0,
        )
        total_events += len(batch)

    print(f"  ✅ Ingested {total_events} historical token events")


async def seed_value_events(client: httpx.AsyncClient, days: int = 30):
    """Seed business value events."""
    print(f"📈 Seeding {days} days of value events...")
    count = 0
    for day_back in range(days, 0, -1):
        n = random.randint(2, 8)
        for _ in range(n):
            event = make_value_event(days_back=day_back)
            await client.post(
                f"{COLLECTOR_URL}/api/v1/value-events",
                json=event,
                timeout=10.0,
            )
            count += 1

    print(f"  ✅ Created {count} value events")


async def add_budget_policies(client: httpx.AsyncClient):
    """Create demo budget policies."""
    print("💰 Creating budget policies...")
    policies = [
        {
            "name": "Search Team Monthly",
            "dimension_type": "team",
            "dimension_value": "search",
            "budget_usd": 1500.0,
            "period": "monthly",
            "warn_threshold_pct": 70.0,
            "critical_threshold_pct": 90.0,
        },
        {
            "name": "GPT-4o Model Limit",
            "dimension_type": "model",
            "dimension_value": "gpt-4o",
            "budget_usd": 3000.0,
            "period": "monthly",
            "warn_threshold_pct": 75.0,
            "critical_threshold_pct": 95.0,
        },
        {
            "name": "Recommendations Team Monthly",
            "dimension_type": "team",
            "dimension_value": "recommendations",
            "budget_usd": 800.0,
            "period": "monthly",
            "warn_threshold_pct": 80.0,
            "critical_threshold_pct": 95.0,
        },
    ]
    for p in policies:
        resp = await client.post(f"{COLLECTOR_URL}/api/v1/budgets", json=p, timeout=10.0)
        if resp.status_code == 201:
            print(f"  ✅ Created budget: {p['name']}")
        elif resp.status_code == 422:
            print(f"  ⏩ Budget already exists (or validation error): {p['name']}")


async def run_live_simulation(client: httpx.AsyncClient, calls: int = 20):
    """Simulate live LLM calls."""
    print(f"\n🤖 Simulating {calls} live LLM calls...")
    costs = []
    for i in range(calls):
        event = make_event(days_back=0)
        resp = await client.post(
            f"{COLLECTOR_URL}/api/v1/events",
            json=event,
            timeout=10.0,
        )
        if resp.status_code == 201:
            data = resp.json()
            costs.append(data["total_cost_usd"])
            print(
                f"  [{i+1:2d}] {event['team']:20s} / {event['feature']:30s} "
                f"| {event['model']:35s} "
                f"| {event['prompt_tokens']:5d}+{event['completion_tokens']:5d} tokens "
                f"| ${data['total_cost_usd']:.5f}"
            )
        await asyncio.sleep(0.05)

    print(f"\n  Total cost for {calls} calls: ${sum(costs):.4f}")


async def print_summary(client: httpx.AsyncClient):
    """Print a cost summary."""
    print("\n📊 Cost Summary (last 30 days):")
    resp = await client.get(f"{COLLECTOR_URL}/api/v1/costs/summary?period=30d", timeout=10.0)
    if resp.status_code == 200:
        data = resp.json()
        print(f"  Total Cost:    ${data['total_cost_usd']:.4f}")
        print(f"  Total Tokens:  {data['total_tokens']:,}")
        print(f"  Total Calls:   {data['call_count']:,}")
        print(f"  Avg/Call:      ${data['avg_cost_per_call']:.6f}")

    print("\n📊 Cost by Team:")
    resp = await client.get(f"{COLLECTOR_URL}/api/v1/costs/by-team?period=30d", timeout=10.0)
    if resp.status_code == 200:
        for item in resp.json()[:5]:
            print(f"  {item['dimension']:20s}: ${item['total_cost_usd']:8.4f} ({item['pct_of_total']:5.1f}%)")

    print("\n📊 Cost by Model:")
    resp = await client.get(f"{COLLECTOR_URL}/api/v1/costs/by-model?period=30d", timeout=10.0)
    if resp.status_code == 200:
        for item in resp.json()[:5]:
            print(f"  {item['dimension']:40s}: ${item['total_cost_usd']:8.4f} ({item['pct_of_total']:5.1f}%)")

    # Trigger ROI computation
    await client.post(f"{COLLECTOR_URL}/api/v1/roi/compute", timeout=30.0)

    print("\n📊 Budget Status:")
    resp = await client.get(f"{COLLECTOR_URL}/api/v1/budgets", timeout=10.0)
    if resp.status_code == 200:
        for b in resp.json():
            bar = "█" * int(b['spend_pct'] / 10) + "░" * (10 - int(b['spend_pct'] / 10))
            print(f"  {b['name']:35s}: [{bar}] {b['spend_pct']:5.1f}% of ${b['budget_usd']:.0f}")


async def main():
    print("=" * 60)
    print("  ATCAP Demo — AI Token Cost Attribution Platform")
    print("=" * 60)
    print(f"  Collector: {COLLECTOR_URL}")

    async with httpx.AsyncClient() as client:
        # Health check
        try:
            resp = await client.get(f"{COLLECTOR_URL}/health", timeout=5.0)
            resp.raise_for_status()
            print("  ✅ Backend is running\n")
        except Exception as e:
            print(f"  ❌ Backend not reachable at {COLLECTOR_URL}: {e}")
            print("  Please start the backend first: uvicorn app.main:app --reload")
            return

        await add_budget_policies(client)
        await seed_historical_data(client, days=30)
        await seed_value_events(client, days=30)
        await run_live_simulation(client, calls=20)

        # Trigger budget evaluation
        await client.post(f"{COLLECTOR_URL}/api/v1/budgets/evaluate", timeout=30.0)

        await print_summary(client)

    print("\n✅ Demo complete! Open http://localhost:3000 to view the dashboard.")


if __name__ == "__main__":
    asyncio.run(main())