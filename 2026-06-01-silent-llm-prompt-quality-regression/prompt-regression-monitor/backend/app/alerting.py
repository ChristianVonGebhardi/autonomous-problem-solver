"""
Alert Router — sends notifications via Slack, PagerDuty, webhook.
"""
import json
import structlog
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.config import settings

logger = structlog.get_logger()


class AlertRouter:
    """Routes drift alerts to configured notification channels."""

    def send_alert(self, alert: dict):
        """Send alert to all configured channels."""
        channels_notified = []

        if settings.slack_webhook_url:
            try:
                self._send_slack(alert)
                channels_notified.append("slack")
            except Exception as e:
                logger.error("slack_alert_failed", error=str(e))

        if settings.pagerduty_routing_key:
            try:
                self._send_pagerduty(alert)
                channels_notified.append("pagerduty")
            except Exception as e:
                logger.error("pagerduty_alert_failed", error=str(e))

        logger.info(
            "alert_sent",
            template=alert.get("template_name"),
            metric=alert.get("metric_name"),
            severity=alert.get("severity"),
            channels=channels_notified,
        )

    def _send_slack(self, alert: dict):
        """Send Slack notification via webhook."""
        severity = alert.get("severity", "warning")
        emoji = {"critical": "🔴", "error": "🟠", "warning": "🟡"}.get(severity, "⚠️")

        baseline = alert.get("baseline_mean", 0)
        current = alert.get("current_mean", 0)
        delta_pct = ((current - baseline) / baseline * 100) if baseline else 0

        message = {
            "text": f"{emoji} *LLM Quality Regression Detected*",
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} LLM Quality Regression — {severity.upper()}",
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Template:*\n`{alert.get('template_name')}`"},
                        {"type": "mrkdwn", "text": f"*Metric:*\n`{alert.get('metric_name')}`"},
                        {"type": "mrkdwn", "text": f"*Baseline Mean:*\n{baseline:.4f}"},
                        {"type": "mrkdwn", "text": f"*Current Mean:*\n{current:.4f} ({delta_pct:+.1f}%)"},
                        {"type": "mrkdwn", "text": f"*Detector:*\nCUSUM + Mann-Whitney U"},
                        {"type": "mrkdwn", "text": f"*P-value:*\n{alert.get('p_value', 'N/A'):.4f}"},
                    ],
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Quality has degraded by *{abs(delta_pct):.1f}%* from baseline. Investigate your prompt or model changes.",
                    },
                },
            ],
        }

        with httpx.Client(timeout=10) as client:
            resp = client.post(
                settings.slack_webhook_url,
                json=message,
            )
            resp.raise_for_status()

    def _send_pagerduty(self, alert: dict):
        """Send PagerDuty event."""
        severity_map = {
            "critical": "critical",
            "error": "error",
            "warning": "warning",
        }

        baseline = alert.get("baseline_mean", 0)
        current = alert.get("current_mean", 0)
        delta_pct = ((current - baseline) / baseline * 100) if baseline else 0

        payload = {
            "routing_key": settings.pagerduty_routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": (
                    f"LLM Quality Regression: {alert.get('template_name')} / "
                    f"{alert.get('metric_name')} degraded {abs(delta_pct):.1f}%"
                ),
                "severity": severity_map.get(alert.get("severity", "warning"), "warning"),
                "source": "prompt-regression-monitor",
                "custom_details": alert,
            },
            "dedup_key": f"{alert.get('template_name')}-{alert.get('metric_name')}",
        }

        with httpx.Client(timeout=10) as client:
            resp = client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )
            resp.raise_for_status()