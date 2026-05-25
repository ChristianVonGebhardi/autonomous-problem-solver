import os
import uuid
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.models import User, Contract, ContractClause
from app.schemas import ContractOut, ContractDetail
from app.auth import get_current_user
from app.services.storage import save_upload_file, get_upload_path
from app.services.document_parser import parse_document, chunk_text, classify_clause
from app.services.embeddings import embed_texts
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/contracts", tags=["contracts"])


@router.post("/upload", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
async def upload_contract(
    file: UploadFile = File(...),
    title: str = Form(...),
    client_name: str = Form(...),
    project_value: float = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate file type
    allowed_extensions = {".pdf", ".docx", ".doc", ".txt"}
    file_ext = Path(file.filename or "").suffix.lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only PDF, DOCX, DOC, and TXT files are supported. Got: {file_ext}"
        )

    # Save file
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    destination = get_upload_path(unique_filename, subfolder="contracts")
    file_path = await save_upload_file(file, destination)

    # Create contract record (initially processing)
    contract = Contract(
        owner_id=current_user.id,
        title=title,
        client_name=client_name,
        file_path=file_path,
        file_name=file.filename,
        project_value=project_value,
        status="processing",
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)

    # Parse and embed inline (could be Celery task in production)
    try:
        raw_text = parse_document(file_path, file.filename or unique_filename)
        contract.raw_text = raw_text[:50000]  # Limit stored text

        # Chunk and embed
        chunks = chunk_text(raw_text)

        if chunks and settings.openai_api_key:
            embeddings = await embed_texts(chunks)

            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                clause = ContractClause(
                    contract_id=contract.id,
                    chunk_index=i,
                    text=chunk,
                    embedding=embedding,
                    clause_type=classify_clause(chunk),
                )
                db.add(clause)
        elif chunks:
            # Store chunks without embeddings if no API key
            for i, chunk in enumerate(chunks):
                clause = ContractClause(
                    contract_id=contract.id,
                    chunk_index=i,
                    text=chunk,
                    clause_type=classify_clause(chunk),
                )
                db.add(clause)

        contract.status = "active"
        await db.commit()
        await db.refresh(contract)

    except Exception as e:
        contract.status = "error"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing contract: {str(e)}"
        )

    # Get clause count
    clause_count_result = await db.execute(
        select(func.count(ContractClause.id)).where(ContractClause.contract_id == contract.id)
    )
    clause_count = clause_count_result.scalar() or 0

    result = ContractOut.model_validate(contract)
    result.clause_count = clause_count
    return result


@router.get("/", response_model=List[ContractOut])
async def list_contracts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Contract)
        .where(Contract.owner_id == current_user.id)
        .order_by(Contract.created_at.desc())
    )
    contracts = result.scalars().all()

    output = []
    for contract in contracts:
        clause_count_result = await db.execute(
            select(func.count(ContractClause.id)).where(
                ContractClause.contract_id == contract.id
            )
        )
        clause_count = clause_count_result.scalar() or 0

        co = ContractOut.model_validate(contract)
        co.clause_count = clause_count
        output.append(co)

    return output


@router.get("/{contract_id}", response_model=ContractDetail)
async def get_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Contract).where(
            Contract.id == contract_id,
            Contract.owner_id == current_user.id,
        )
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    clause_count_result = await db.execute(
        select(func.count(ContractClause.id)).where(
            ContractClause.contract_id == contract.id
        )
    )
    clause_count = clause_count_result.scalar() or 0

    result_out = ContractDetail.model_validate(contract)
    result_out.clause_count = clause_count
    return result_out


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Contract).where(
            Contract.id == contract_id,
            Contract.owner_id == current_user.id,
        )
    )
    contract = result.scalar_one_or_none()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    await db.delete(contract)
    await db.commit()