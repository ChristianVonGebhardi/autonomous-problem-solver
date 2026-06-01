"""
Drift Detector — CUSUM and Mann-Whitney U tests over rolling metric windows.
"""
import uuid
import numpy as np
import structlog
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Tuple
from scipy import stats

from app.config import settings

logger = structlog.get_logger()


class DriftDetector:
    """
    Detects quality regressions using:
    1. CUSUM (cumulative sum control chart) — sequential change detection
    2. Mann-Whitney U test — non-parametric comparison of distributions
    """

    def __init__(self, db_session):
        self.db = db_session

    def detect(self, template) -> List[dict]:
        """Run drift detection for all metrics of a template."""
        from app.models import QualityScore, DriftAlert
        from sqlalchemy import select, func

        now = datetime.now(timezone.utc)
        baseline_start = now - timedelta(hours=settings.baseline_window_hours)
        detection_start = now - timedelta(hours=settings.detection_window_hours)

        # Get metric names for this template
        metric_rows = self.db.execute(
            select(QualityScore.metric_name)
            .where(QualityScore.template_id == template.id)
            .distinct()
        ).scalars().all()

        alerts = []
        for metric_name in metric_rows:
            alert = self._detect_metric(
                template,
                metric_name,
                baseline_start,
                detection_start,
                now,
            )
            if alert:
                alerts.append(alert)

        return alerts

    def _detect_metric(
        self,
        template,
        metric_name: str,
        baseline_start: datetime,
        detection_start: datetime,
        now: datetime,
    ) -> Optional[dict]:
        """Detect drift for a single metric."""
        from app.models import QualityScore, DriftAlert
        from sqlalchemy import select

        # Fetch baseline scores (before detection window)
        baseline_scores = self.db.execute(
            select(QualityScore.score, QualityScore.scored_at)
            .where(QualityScore.template_id == template.id)
            .where(QualityScore.metric_name == metric_name)
            .where(QualityScore.scored_at >= baseline_start)
            .where(QualityScore.scored_at < detection_start)
            .order_by(QualityScore.scored_at)
        ).all()

        # Fetch recent scores (detection window)
        recent_scores = self.db.execute(
            select(QualityScore.score, QualityScore.scored_at)
            .where(QualityScore.template_id == template.id)
            .where(QualityScore.metric_name == metric_name)
            .where(QualityScore.scored_at >= detection_start)
            .order_by(QualityScore.scored_at)
        ).all()

        if (len(baseline_scores) < settings.min_samples_for_detection or
                len(recent_scores) < 3):
            return None

        baseline_arr = np.array([r.score for r in baseline_scores])
        recent_arr = np.array([r.score for r in recent_scores])

        # Check for existing unacknowledged alert (avoid spam)
        existing_alert = self.db.execute(
            select(DriftAlert)
            .where(DriftAlert.template_id == template.id)
            .where(DriftAlert.metric_name == metric_name)
            .where(DriftAlert.acknowledged == False)
            .where(DriftAlert.created_at >= now - timedelta(hours=1))
        ).scalar_one_or_none()

        if existing_alert:
            return None

        # Run CUSUM
        cusum_stat, cusum_triggered = self._cusum_test(baseline_arr, recent_arr)

        # Run Mann-Whitney U
        p_value, mw_triggered = self._mann_whitney_test(baseline_arr, recent_arr)

        baseline_mean = float(np.mean(baseline_arr))
        current_mean = float(np.mean(recent_arr))
        delta = current_mean - baseline_mean

        # Alert if either detector triggers AND quality actually degraded
        regression_threshold = -0.05  # 5% relative degradation
        is_regression = delta < regression_threshold

        if (cusum_triggered or mw_triggered) and is_regression:
            severity = self._compute_severity(delta, baseline_mean)

            alert = DriftAlert(
                template_id=template.id,
                template_name=template.name,
                metric_name=metric_name,
                detector_type="cusum+mann_whitney" if (cusum_triggered and mw_triggered) else (
                    "cusum" if cusum_triggered else "mann_whitney"
                ),
                severity=severity,
                baseline_mean=baseline_mean,
                current_mean=current_mean,
                p_value=float(p_value),
                cusum_stat=float(cusum_stat),
                evidence={
                    "baseline_samples": len(baseline_scores),
                    "recent_samples": len(recent_scores),
                    "baseline_std": float(np.std(baseline_arr)),
                    "current_std": float(np.std(recent_arr)),
                    "delta": float(delta),
                    "delta_pct": float(delta / baseline_mean * 100) if baseline_mean != 0 else 0,
                    "cusum_triggered": cusum_triggered,
                    "mw_triggered": mw_triggered,
                    "mw_p_value": float(p_value),
                    "cusum_stat": float(cusum_stat),
                },
            )
            self.db.add(alert)
            self.db.commit()
            self.db.refresh(alert)

            logger.warning(
                "drift_detected",
                template=template.name,
                metric=metric_name,
                severity=severity,
                baseline_mean=round(baseline_mean, 4),
                current_mean=round(current_mean, 4),
                delta_pct=round(delta / baseline_mean * 100 if baseline_mean else 0, 1),
            )

            return {
                "id": str(alert.id),
                "template_name": template.name,
                "metric_name": metric_name,
                "severity": severity,
                "baseline_mean": baseline_mean,
                "current_mean": current_mean,
                "delta": delta,
                "p_value": p_value,
                "cusum_stat": cusum_stat,
            }

        return None

    def _cusum_test(
        self, baseline: np.ndarray, recent: np.ndarray
    ) -> Tuple[float, bool]:
        """
        Two-sided CUSUM test for detecting shifts in mean.
        Returns (cusum_statistic, triggered).
        """
        target_mean = float(np.mean(baseline))
        sigma = max(float(np.std(baseline)), 1e-6)

        k = settings.cusum_slack * sigma  # allowance
        h = settings.cusum_threshold * sigma  # threshold

        # Cumulative sums for downward shift (quality decrease)
        S_neg = 0.0
        S_neg_max = 0.0

        for x in recent:
            S_neg = max(0, S_neg + (target_mean - x) - k)
            S_neg_max = max(S_neg_max, S_neg)

        triggered = S_neg_max >= h
        return S_neg_max, triggered

    def _mann_whitney_test(
        self, baseline: np.ndarray, recent: np.ndarray
    ) -> Tuple[float, bool]:
        """
        One-sided Mann-Whitney U test: tests if recent scores are lower.
        Returns (p_value, triggered).
        """
        try:
            statistic, p_value = stats.mannwhitneyu(
                recent, baseline,
                alternative="less",  # recent < baseline
            )
            triggered = p_value < settings.mann_whitney_alpha
            return float(p_value), triggered
        except Exception as e:
            logger.warning("mann_whitney_failed", error=str(e))
            return 1.0, False

    def _compute_severity(self, delta: float, baseline_mean: float) -> str:
        """Compute alert severity based on magnitude of regression."""
        if baseline_mean == 0:
            return "warning"
        pct_change = abs(delta / baseline_mean)
        if pct_change >= 0.30:
            return "critical"
        elif pct_change >= 0.15:
            return "error"
        else:
            return "warning"