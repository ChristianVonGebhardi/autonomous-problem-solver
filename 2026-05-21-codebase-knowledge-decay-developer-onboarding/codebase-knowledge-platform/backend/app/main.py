import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.db.postgres import init_db
from app.db.neo4j_client import neo4j_client
from app.db.qdrant_client import qdrant_client
from app.api.routes import ingest, query, graph, health

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all connections on startup."""
    logger.info("Starting Codebase Knowledge Platform", demo_mode=settings.demo_mode)

    # PostgreSQL — create tables
    try:
        await init_db()
        logger.info("PostgreSQL initialized")
    except Exception as e:
        logger.warning("PostgreSQL init failed", error=str(e))

    # Neo4j
    try:
        await neo4j_client.connect()
        await neo4j_client.create_indexes()
        logger.info("Neo4j connected and indexes created")
    except Exception as e:
        logger.warning("Neo4j not available", error=str(e))

    # Qdrant
    try:
        await qdrant_client.connect()
        await qdrant_client.create_collections()
        logger.info("Qdrant connected and collections ready")
    except Exception as e:
        logger.warning("Qdrant not available", error=str(e))

    yield

    # Cleanup
    try:
        await neo4j_client.close()
    except Exception:
        pass
    logger.info("Shutdown complete")


app = FastAPI(
    title="Codebase Knowledge Intelligence Platform",
    description="AI-powered knowledge graph for codebases",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(ingest.router, prefix="/api/v1/ingest", tags=["ingestion"])
app.include_router(query.router, prefix="/api/v1/query", tags=["query"])
app.include_router(graph.router, prefix="/api/v1/graph", tags=["graph"])


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception", error=str(exc), path=str(request.url.path))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )