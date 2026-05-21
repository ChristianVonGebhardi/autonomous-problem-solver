import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db.session import init_db
from app.graph.neo4j_client import get_neo4j_client
from app.vector.qdrant_client import get_qdrant_client
from app.api.v1 import ingest, query, graph, repositories

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all connections on startup."""
    logger.info("Starting Codebase Knowledge Platform API")

    # Initialize database
    await init_db()

    # Initialize Neo4j schema
    neo4j = get_neo4j_client()
    await neo4j.initialize_schema()

    # Initialize Qdrant collection
    qdrant = get_qdrant_client()
    await qdrant.initialize_collection()

    logger.info("All services initialized")
    yield

    logger.info("Shutting down")
    await neo4j.close()


app = FastAPI(
    title="Codebase Knowledge Intelligence Platform",
    description="AI-powered knowledge graph for developer onboarding and codebase understanding",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(ingest.router, prefix="/api/v1/ingest", tags=["Ingestion"])
app.include_router(query.router, prefix="/api/v1/query", tags=["Query"])
app.include_router(graph.router, prefix="/api/v1/graph", tags=["Graph"])
app.include_router(repositories.router, prefix="/api/v1/repositories", tags=["Repositories"])


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}