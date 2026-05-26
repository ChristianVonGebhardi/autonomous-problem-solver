import os
import uuid
import tempfile
import structlog
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.db.postgres import get_db, Repository, IngestionJob
from app.workers.tasks import ingest_git_repo, ingest_github_repo
from app.config import settings

logger = structlog.get_logger()
router = APIRouter()


class GitIngestRequest(BaseModel):
    repo_path: str = Field(..., description="Absolute path to local git repository")
    repo_name: str = Field(..., description="Name identifier for the repository")


class GitHubIngestRequest(BaseModel):
    repo_url: str = Field(..., description="GitHub HTTPS URL")
    repo_name: str = Field(..., description="Name identifier for the repository")


class IngestResponse(BaseModel):
    job_id: str
    repo_name: str
    status: str
    message: str


@router.post("/git", response_model=IngestResponse)
async def ingest_git_repository(
    request: GitIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Ingest a local git repository."""
    # Validate path exists
    if not os.path.exists(request.repo_path):
        raise HTTPException(status_code=400, detail=f"Path does not exist: {request.repo_path}")

    if not os.path.exists(os.path.join(request.repo_path, ".git")):
        # Try to find git root
        parent = os.path.dirname(request.repo_path)
        if not os.path.exists(os.path.join(parent, ".git")):
            raise HTTPException(status_code=400, detail="Not a git repository (no .git directory)")

    # Create or update repository record
    repo = Repository(
        id=str(uuid.uuid4()),
        name=request.repo_name,
        repo_path=request.repo_path,
        status="pending",
    )
    db.add(repo)
    try:
        await db.flush()
    except Exception:
        # May already exist — update it
        await db.execute(
            update(Repository)
            .where(Repository.name == request.repo_name)
            .values(repo_path=request.repo_path, status="pending")
        )
        result = await db.execute(select(Repository).where(Repository.name == request.repo_name))
        repo = result.scalar_one()

    # Create ingestion job
    job = IngestionJob(
        id=str(uuid.uuid4()),
        repo_name=request.repo_name,
        job_type="git",
        status="pending",
    )
    db.add(job)
    await db.flush()

    # Update repo with status
    await db.execute(
        update(Repository)
        .where(Repository.name == request.repo_name)
        .values(status="ingesting")
    )

    await db.commit()

    # Dispatch Celery task
    try:
        task = ingest_git_repo.delay(request.repo_path, request.repo_name, job.id)
        await db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job.id)
            .values(celery_task_id=task.id, status="running")
        )
        await db.commit()
    except Exception as e:
        logger.warning("Could not dispatch to Celery, running inline", error=str(e))
        # Run inline as fallback (blocking)
        from app.services.git_ingestion import git_ingestion_service
        import asyncio
        result = await git_ingestion_service.ingest_repository(request.repo_path, request.repo_name)
        await db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job.id)
            .values(status="completed", progress=100)
        )
        await db.execute(
            update(Repository)
            .where(Repository.name == request.repo_name)
            .values(status="ready", last_ingested_at=datetime.now(timezone.utc))
        )
        await db.commit()

    return IngestResponse(
        job_id=job.id,
        repo_name=request.repo_name,
        status="running",
        message=f"Ingestion started for '{request.repo_name}'",
    )


@router.post("/github", response_model=IngestResponse)
async def ingest_github_repository(
    request: GitHubIngestRequest,
    db: AsyncSession = Depends(get_db),
):
    """Clone and ingest a GitHub repository."""
    # Create local clone path
    clone_dir = os.path.join(tempfile.gettempdir(), "repos", request.repo_name)
    os.makedirs(clone_dir, exist_ok=True)

    # Create DB records
    repo = Repository(
        id=str(uuid.uuid4()),
        name=request.repo_name,
        repo_url=request.repo_url,
        repo_path=clone_dir,
        status="pending",
    )
    db.add(repo)
    try:
        await db.flush()
    except Exception:
        await db.execute(
            update(Repository)
            .where(Repository.name == request.repo_name)
            .values(repo_url=request.repo_url, repo_path=clone_dir, status="pending")
        )

    job = IngestionJob(
        id=str(uuid.uuid4()),
        repo_name=request.repo_name,
        job_type="github",
        status="pending",
    )
    db.add(job)
    await db.flush()

    await db.execute(
        update(Repository)
        .where(Repository.name == request.repo_name)
        .values(status="ingesting")
    )
    await db.commit()

    # Dispatch Celery task
    try:
        task = ingest_github_repo.delay(request.repo_url, request.repo_name, job.id, clone_dir)
        await db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job.id)
            .values(celery_task_id=task.id, status="running")
        )
        await db.commit()
    except Exception as e:
        logger.warning("Could not dispatch GitHub task to Celery", error=str(e))
        # Inline fallback
        from app.services.github_ingestion import github_ingestion_service
        from app.services.git_ingestion import git_ingestion_service
        
        cloned = await github_ingestion_service.clone_repo(request.repo_url, clone_dir)
        if cloned:
            await git_ingestion_service.ingest_repository(clone_dir, request.repo_name)
        
        await db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job.id)
            .values(status="completed", progress=100)
        )
        await db.execute(
            update(Repository)
            .where(Repository.name == request.repo_name)
            .values(status="ready", last_ingested_at=datetime.now(timezone.utc))
        )
        await db.commit()

    return IngestResponse(
        job_id=job.id,
        repo_name=request.repo_name,
        status="running",
        message=f"GitHub ingestion started for '{request.repo_name}'",
    )


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get ingestion job status."""
    result = await db.execute(select(IngestionJob).where(IngestionJob.id == job_id))
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Also check Celery task state
    celery_state = None
    if job.celery_task_id:
        try:
            from app.workers.celery_app import celery_app
            task = celery_app.AsyncResult(job.celery_task_id)
            celery_state = {
                "state": task.state,
                "info": task.info if isinstance(task.info, dict) else {},
            }
        except Exception:
            pass

    return {
        "job_id": job.id,
        "repo_name": job.repo_name,
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "error_message": job.error_message,
        "celery_state": celery_state,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("/repositories")
async def list_repositories(db: AsyncSession = Depends(get_db)):
    """List all ingested repositories."""
    result = await db.execute(select(Repository))
    repos = result.scalars().all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "repo_path": r.repo_path,
            "repo_url": r.repo_url,
            "status": r.status,
            "file_count": r.file_count,
            "commit_count": r.commit_count,
            "last_ingested_at": r.last_ingested_at.isoformat() if r.last_ingested_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in repos
    ]