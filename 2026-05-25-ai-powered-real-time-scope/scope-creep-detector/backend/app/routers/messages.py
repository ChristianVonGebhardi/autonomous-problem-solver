from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import User, Contract, Message
from app.schemas import MessageCreate, MessageOut
from app.auth import get_current_user
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/messages", tags=["messages"])


async def process_message_inline(
    message_id: str,
    contract_id: str,
    user_id: str,
) -> None:
    """Process a message for scope creep in background (uses its own DB session)."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from app.services.scope_analyzer import (
        analyze_message_for_scope_creep,
        generate_change_order_content,
    )
    from app.services.pdf_generator import generate_change_order_pdf
    from app.models import ChangeOrder, ViolationStatus, User as UserModel
    import structlog

    logger = structlog.get_logger()

    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with AsyncSessionLocal() as db:
            msg_result = await db.execute(select(Message).where(Message.id == message_id))
            message = msg_result.scalar_one_or_none()

            contract_result = await db.execute(
                select(Contract).where(Contract.id == contract_id)
            )
            contract = contract_result.scalar_one_or_none()

            if not message or not contract:
                logger.error("message_or_contract_not_found", message_id=message_id)
                return

            violation = await analyze_message_for_scope_creep(db, message, contract)

            message.analyzed = True
            await db.commit()

            if violation:
                user_result = await db.execute(
                    select(UserModel).where(UserModel.id == user_id)
                )
                user = user_result.scalar_one_or_none()

                cited_clause = ""
                if violation.cited_clauses and len(violation.cited_clauses) > 0:
                    first = violation.cited_clauses[0]
                    cited_clause = (
                        first.get("text", "") if isinstance(first, dict) else str(first)
                    )

                co_content = await generate_change_order_content(
                    freelancer_name=user.full_name if user else "Freelancer",
                    client_name=contract.client_name,
                    project_title=contract.title,
                    hourly_rate=user.hourly_rate if user else 150.0,
                    out_of_scope_work=violation.out_of_scope_work,
                    estimated_hours=violation.estimated_hours or 2.0,
                    cited_clause=cited_clause,
                )

                hourly_rate = user.hourly_rate if user else 150.0
                estimated_hours = violation.estimated_hours or 2.0

                change_order = ChangeOrder(
                    violation_id=violation.id,
                    owner_id=violation.owner_id,
                    title=co_content["title"],
                    description=co_content["description"],
                    scope_addition=co_content["scope_addition"],
                    estimated_hours=estimated_hours,
                    hourly_rate=hourly_rate,
                    total_cost=estimated_hours * hourly_rate,
                    terms=co_content.get("terms", "Payment due within 15 days of approval."),
                )
                db.add(change_order)
                violation.status = ViolationStatus.CHANGE_ORDER_CREATED

                await db.commit()
                await db.refresh(change_order)

                # Generate PDF
                pdf_path = (
                    f"{settings.upload_dir}/change_orders/"
                    f"CO-{str(change_order.id)[:8].upper()}.pdf"
                )
                pdf_data = {
                    "freelancer_name": user.full_name if user else "Freelancer",
                    "co_number": str(change_order.id)[:8].upper(),
                    "date_issued": change_order.created_at.strftime("%B %d, %Y"),
                    "project_title": contract.title,
                    "client_name": contract.client_name,
                    "description": change_order.description,
                    "scope_addition": change_order.scope_addition,
                    "estimated_hours": change_order.estimated_hours,
                    "hourly_rate": change_order.hourly_rate,
                    "total_cost": change_order.total_cost,
                    "terms": change_order.terms,
                    "professional_note": co_content.get("professional_note", ""),
                }
                success = generate_change_order_pdf(pdf_data, pdf_path)
                if success:
                    change_order.pdf_path = pdf_path
                    await db.commit()

                # Push WebSocket notification
                try:
                    from app.websocket_manager import manager

                    await manager.send_to_user(
                        str(user_id),
                        {
                            "type": "violation_detected",
                            "data": {
                                "violation_id": str(violation.id),
                                "severity": violation.severity.value,
                                "summary": violation.summary,
                                "estimated_cost": violation.estimated_cost,
                                "change_order_id": str(change_order.id),
                                "contract_title": contract.title,
                                "client_name": contract.client_name,
                            },
                        },
                    )
                except Exception as ws_err:
                    logger.warning("ws_notify_failed", error=str(ws_err))

                logger.info("change_order_created", change_order_id=str(change_order.id))

    except Exception as e:
        logger.error("process_message_error", error=str(e), exc_info=True)
    finally:
        await engine.dispose()


@router.post("/analyze", response_model=MessageOut, status_code=status.HTTP_201_CREATED)
async def analyze_message(
    message_data: MessageCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a client message for scope creep analysis."""
    contract_result = await db.execute(
        select(Contract).where(
            Contract.id == str(message_data.contract_id),
            Contract.owner_id == current_user.id,
        )
    )
    contract = contract_result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    if contract.status != "active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Contract must be in 'active' status to analyze messages. Current status: {contract.status}",
        )

    message = Message(
        owner_id=current_user.id,
        contract_id=message_data.contract_id,
        source=message_data.source,
        sender_name=message_data.sender_name,
        sender_email=message_data.sender_email,
        subject=message_data.subject,
        content=message_data.content,
        analyzed=False,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    # Process in background using a fresh DB session
    if settings.openai_api_key:
        background_tasks.add_task(
            process_message_inline,
            str(message.id),
            str(message_data.contract_id),
            str(current_user.id),
        )

    return MessageOut.model_validate(message)


@router.get("/", response_model=List[MessageOut])
async def list_messages(
    contract_id: str = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Message).where(Message.owner_id == current_user.id)
    if contract_id:
        query = query.where(Message.contract_id == contract_id)
    query = query.order_by(Message.created_at.desc())

    result = await db.execute(query)
    messages = result.scalars().all()
    return [MessageOut.model_validate(m) for m in messages]


@router.get("/{message_id}", response_model=MessageOut)
async def get_message(
    message_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Message).where(
            Message.id == message_id,
            Message.owner_id == current_user.id,
        )
    )
    message = result.scalar_one_or_none()
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    return MessageOut.model_validate(message)