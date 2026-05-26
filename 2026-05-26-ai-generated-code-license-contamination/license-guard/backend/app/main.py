import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.config import settings
from app.routes import scan, corpus, dashboard, health

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    logger.info("LicenseGuard API starting up...")
    
    # Pre-load embedding model
    try:
        from app.detector import get_embedding_model
        model = get_embedding_model(settings.embedding_model)
        if model:
            logger.info(f"Embedding model loaded: {settings.embedding_model}")
        else:
            logger.warning("Embedding model not available")
    except Exception as e:
        logger.warning(f"Could not pre-load embedding model: {e}")
    
    yield
    
    logger.info("LicenseGuard API shutting down...")


app = FastAPI(
    title="LicenseGuard API",
    description="AI-Generated Code License Contamination Detection",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(scan.router, prefix="/api/v1", tags=["scanning"])
app.include_router(corpus.router, prefix="/api/v1", tags=["corpus"])
app.include_router(dashboard.router, prefix="/api/v1", tags=["dashboard"])


@app.get("/")
async def root():
    return {
        "service": "LicenseGuard",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }