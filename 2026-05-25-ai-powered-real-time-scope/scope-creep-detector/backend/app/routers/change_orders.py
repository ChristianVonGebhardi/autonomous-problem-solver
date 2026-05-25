from datetime import datetime
from typing import List, Optional
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, ChangeOrder, ChangeOrderStatus, Violation
from app.schemas import ChangeOrderOut, ChangeOrderUpdate
from app.auth import get_current_user
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/change-orders", tags=["change-orders"])


@router.get("/", response_model=List[ChangeOrderOut])
async def list_change_orders(
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(ChangeOrder).where(ChangeOrder.owner_id == current_user.id)
    if status:
        query = query.where(ChangeOrder.status == status)
    query = query.order_by(ChangeOrder.created_at.desc())

    result = await db.execute(query)
    orders = result.scalars().all()
    return [ChangeOrderOut.model_validate(o) for o in orders]


@router.get("/{co_id}", response_model=ChangeOrderOut)
async def get_change_order(
    co_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChangeOrder).where(
            ChangeOrder.id == co_id,
            ChangeOrder.owner_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Change order not found")
    return ChangeOrderOut.model_validate(order)


@router.patch("/{co_id}", response_model=ChangeOrderOut)
async def update_change_order(
    co_id: str,
    updates: ChangeOrderUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ChangeOrder).where(
            ChangeOrder.id == co_id,
            ChangeOrder.owner_id == current_user.id,
            ChangeOrder.status == ChangeOrderStatus.DRAFT,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Change order not found or not editable")

    update_data = updates.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(order, field, value)

    # Recalculate total if hours or rate changed
    if "estimated_hours" in update_data or "hourly_rate" in update_data:
        order.total_cost = order.estimated_hours * order.hourly_rate

    order.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(order)
    return ChangeOrderOut.model_validate(order)


@router.post("/{co_id}/approve", response_model=ChangeOrderOut)
async def approve_change_order(
    co_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a change order (and optionally send via email if SendGrid configured)."""
    result = await db.execute(
        select(ChangeOrder).where(
            ChangeOrder.id == co_id,
            ChangeOrder.owner_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Change order not found")

    order.status = ChangeOrderStatus.APPROVED
    order.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(order)

    # Optionally notify via SendGrid
    if settings.sendgrid_api_key:
        try:
            await _send_change_order_email(order, current_user, db)
        except Exception:
            pass  # Don't fail the approval if email fails

    return ChangeOrderOut.model_validate(order)


@router.post("/{co_id}/send", response_model=ChangeOrderOut)
async def send_change_order(
    co_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark change order as sent."""
    result = await db.execute(
        select(ChangeOrder).where(
            ChangeOrder.id == co_id,
            ChangeOrder.owner_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Change order not found")

    order.status = ChangeOrderStatus.SENT
    order.sent_at = datetime.utcnow()
    order.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(order)
    return ChangeOrderOut.model_validate(order)


@router.get("/{co_id}/pdf")
async def download_pdf(
    co_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download the change order PDF (or HTML fallback)."""
    result = await db.execute(
        select(ChangeOrder).where(
            ChangeOrder.id == co_id,
            ChangeOrder.owner_id == current_user.id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=404, detail="Change order not found")

    if not order.pdf_path:
        raise HTTPException(status_code=404, detail="PDF not yet generated")

    pdf_path = order.pdf_path

    # Try PDF first
    if Path(pdf_path).exists():
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"change-order-{co_id[:8]}.pdf",
        )

    # Try HTML fallback
    html_path = pdf_path.replace(".pdf", ".html")
    if Path(html_path).exists():
        return FileResponse(
            html_path,
            media_type="text/html",
            filename=f"change-order-{co_id[:8]}.html",
        )

    raise HTTPException(status_code=404, detail="Change order file not found on disk")


async def _send_change_order_email(order: ChangeOrder, user: User, db: AsyncSession):
    """Send change order notification via SendGrid (optional)."""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)

        message = Mail(
            from_email=settings.from_email,
            to_emails=user.email,
            subject=f"Change Order Ready: {order.title}",
            html_content=f"""
            <h2>Change Order Generated</h2>
            <p>A new change order has been generated: <strong>{order.title}</strong></p>
            <p><strong>Total Cost:</strong> ${order.total_cost:,.2f}</p>
            <p><strong>Hours:</strong> {order.estimated_hours} @ ${order.hourly_rate}/hr</p>
            <p>Please log in to your ScopeGuard dashboard to review and send it to your client.</p>
            """,
        )
        sg.send(message)
    except Exception as e:
        import structlog
        structlog.get_logger().warning("email_send_failed", error=str(e))