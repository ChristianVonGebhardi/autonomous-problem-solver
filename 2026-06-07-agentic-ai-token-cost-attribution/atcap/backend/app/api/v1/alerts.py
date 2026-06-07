"""Alert testing and notification endpoints."""
from fastapi import APIRouter
from app.services.alerting import send_test_alert

router = APIRouter()


@router.post("/alerts/test")
async def test_alert():
    """Send a test alert to verify Slack integration."""
    result = await send_test_alert()
    return result