import asyncio
import json
from celery import Celery
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "scope_creep_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="analyze_message")
def analyze_message_task(message_id: str, contract_id: str, user_id: str):
    """Celery task to analyze a message for scope creep."""
    return asyncio.run(_analyze_message_async(message_id, contract_id, user_id))


async def _analyze_message_async(message_id: str, contract_id: str, user_id: str):
    """Async implementation of message analysis."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import select
    from app.models import Message, Contract, Violation, ChangeOrder, ViolationStatus
    from app.services.scope_analyzer import analyze_message_for_scope_creep, generate_change_order_content
    from app.services.pdf_generator import generate_change_order_pdf
    import structlog
    
    logger = structlog.get_logger()
    
    engine = create_async_engine(settings.database_url)
    AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with AsyncSessionLocal() as db:
        # Load message and contract
        msg_result = await db.execute(select(Message).where(Message.id == message_id))
        message = msg_result.scalar_one_or_none()
        
        contract_result = await db.execute(select(Contract).where(Contract.id == contract_id))
        contract = contract_result.scalar_one_or_none()
        
        if not message or not contract:
            logger.error("message_or_contract_not_found", message_id=message_id, contract_id=contract_id)
            return {"error": "Message or contract not found"}
        
        # Analyze for scope creep
        violation = await analyze_message_for_scope_creep(db, message, contract)
        
        # Mark message as analyzed
        message.analyzed = True
        await db.commit()
        
        if violation:
            # Generate change order
            from app.models import User
            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()
            
            cited_clause = ""
            if violation.cited_clauses:
                cited_clause = violation.cited_clauses[0].get("text", "") if isinstance(violation.cited_clauses[0], dict) else str(violation.cited_clauses[0])
            
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
            
            # Update violation status
            violation.status = ViolationStatus.CHANGE_ORDER_CREATED
            
            await db.commit()
            await db.refresh(change_order)
            
            # Generate PDF
            pdf_path = f"{settings.upload_dir}/change_orders/CO-{str(change_order.id)[:8].upper()}.pdf"
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
            
            logger.info("change_order_created", change_order_id=str(change_order.id))
            
            # Try to send WebSocket notification
            try:
                import redis as sync_redis
                r = sync_redis.from_url(settings.redis_url)
                notification = {
                    "type": "violation_detected",
                    "user_id": user_id,
                    "data": {
                        "violation_id": str(violation.id),
                        "severity": violation.severity.value,
                        "summary": violation.summary,
                        "estimated_cost": violation.estimated_cost,
                        "change_order_id": str(change_order.id),
                        "contract_title": contract.title,
                        "client_name": contract.client_name,
                    }
                }
                r.publish("violations", json.dumps(notification))
            except Exception as e:
                logger.warning("redis_publish_failed", error=str(e))
            
            return {"violation_id": str(violation.id), "change_order_id": str(change_order.id)}
        
        return {"message": "No scope violation detected"}
    
    await engine.dispose()