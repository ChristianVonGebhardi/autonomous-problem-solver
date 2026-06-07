"""Slack/Teams alerting service for budget breaches."""
import logging
from typing import Optional
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

LEVEL_COLORS = {
    "warn": "#FFA500",
    "critical": "#FF0000",
}

LEVEL_EMOJI = {
    "warn": "⚠️",
    "critical": "🚨",
}


async def send_budget_alert(
    policy_name: str,
    dimension_type: str,
    dimension_value: Optional[str],
    current_spend: float,
    budget: float,
    spend_pct: float,
    alert_level: str,
    period: str,
) -> bool:
    """Send a budget breach alert to Slack. Returns True if sent successfully."""
    if not settings.SLACK_WEBHOOK_URL:
        logger.info(f"[Slack] Budget alert (no webhook configured): {policy_name} at {spend_pct:.1f}%")
        return False

    emoji = LEVEL_EMOJI.get(alert_level, "⚠️")
    color = LEVEL_COLORS.get(alert_level, "#FFA500")

    scope_text = f"{dimension_type}: {dimension_value}" if dimension_value else "global"

    payload = {
        "attachments": [
            {
                "color": color,
                "title": f"{emoji} ATCAP Budget Alert — {alert_level.upper()}",
                "fields": [
                    {"title": "Policy", "value": policy_name, "short": True},
                    {"title": "Scope", "value": scope_text, "short": True},
                    {"title": "Current Spend", "value": f"${current_spend:.2f}", "short": True},
                    {"title": "Budget", "value": f"${budget:.2f} ({period})", "short": True},
                    {"title": "Consumed", "value": f"{spend_pct:.1f}%", "short": True},
                ],
                "footer": "ATCAP | AI Token Cost Attribution Platform",
                "ts": int(__import__('time').time()),
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.SLACK_WEBHOOK_URL,
                json=payload,
            )
            response.raise_for_status()
            logger.info(f"Slack alert sent for {policy_name}")
            return True
    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}")
        return False


async def send_test_alert() -> dict:
    """Send a test alert to verify Slack integration."""
    sent = await send_budget_alert(
        policy_name="Test Policy",
        dimension_type="team",
        dimension_value="engineering",
        current_spend=850.0,
        budget=1000.0,
        spend_pct=85.0,
        alert_level="warn",
        period="monthly",
    )
    return {"sent": sent, "webhook_configured": bool(settings.SLACK_WEBHOOK_URL)}