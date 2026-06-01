"""
OpenAI-compatible reverse proxy interceptor.
Forwards requests to the upstream LLM provider, captures request/response pairs,
and enqueues async quality scoring jobs.
"""
import json
import time
import hashlib
import structlog
from typing import Optional
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import httpx

from app.config import settings
from app.worker import score_inference_async

logger = structlog.get_logger()

app = FastAPI(title="LLM Quality Monitor - Proxy", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# HTTP client for upstream calls
upstream_client = httpx.AsyncClient(
    base_url=settings.llm_provider_base_url,
    timeout=120.0,
)


def extract_template_name(request_body: dict, headers: dict) -> str:
    """Extract template name from request metadata."""
    # Check custom header first
    template = headers.get("x-prompt-template", "")
    if template:
        return template

    # Check request body metadata
    metadata = request_body.get("metadata", {})
    if isinstance(metadata, dict):
        template = metadata.get("template_name", "")
        if template:
            return template

    # Fall back to model + system prompt hash
    model = request_body.get("model", "unknown")
    messages = request_body.get("messages", [])
    system_msgs = [m.get("content", "") for m in messages if m.get("role") == "system"]
    if system_msgs:
        system_hash = hashlib.md5(system_msgs[0].encode()).hexdigest()[:8]
        return f"{model}-{system_hash}"

    return "default"


def extract_content(response_body: dict) -> Optional[str]:
    """Extract text content from OpenAI response."""
    try:
        choices = response_body.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            return msg.get("content", "")
    except Exception:
        pass
    return None


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info("proxy_request", method=request.method, path=request.url.path)
    response = await call_next(request)
    return response


@app.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]
)
async def proxy_request(path: str, request: Request):
    """Proxy all requests to the upstream LLM provider."""
    start_time = time.time()

    # Read request body
    body_bytes = await request.body()
    request_body = {}
    if body_bytes:
        try:
            request_body = json.loads(body_bytes)
        except json.JSONDecodeError:
            pass

    # Build upstream headers
    upstream_headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ("host", "content-length", "transfer-encoding"):
            upstream_headers[key] = value

    # Ensure authorization header is present
    if "authorization" not in upstream_headers and settings.openai_api_key:
        upstream_headers["authorization"] = f"Bearer {settings.openai_api_key}"

    # Extract template name before forwarding
    template_name = extract_template_name(request_body, dict(request.headers))

    # Handle streaming - for now, disable streaming to capture full response
    if request_body.get("stream"):
        request_body["stream"] = False
        body_bytes = json.dumps(request_body).encode()
        upstream_headers["content-length"] = str(len(body_bytes))

    try:
        # Forward to upstream
        upstream_response = await upstream_client.request(
            method=request.method,
            url=f"/{path}",
            content=body_bytes,
            headers=upstream_headers,
            params=dict(request.query_params),
        )

        latency_ms = (time.time() - start_time) * 1000

        # Parse response
        response_body = {}
        response_content = upstream_response.content
        if upstream_response.headers.get("content-type", "").startswith("application/json"):
            try:
                response_body = upstream_response.json()
            except Exception:
                pass

        # Enqueue scoring job asynchronously (non-blocking)
        if (
            path in ("v1/chat/completions", "chat/completions")
            and request.method == "POST"
            and response_body
            and "choices" in response_body
        ):
            try:
                output_text = extract_content(response_body)
                usage = response_body.get("usage", {})

                score_inference_async.apply_async(
                    kwargs={
                        "template_name": template_name,
                        "request_payload": request_body,
                        "response_payload": response_body,
                        "output_text": output_text,
                        "model": request_body.get("model", "unknown"),
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "latency_ms": latency_ms,
                    },
                    countdown=0,
                )
                logger.info(
                    "scoring_job_enqueued",
                    template=template_name,
                    latency_ms=round(latency_ms, 1),
                )
            except Exception as e:
                # Never fail the proxy due to scoring errors
                logger.error("scoring_enqueue_failed", error=str(e))

        # Return upstream response
        response_headers = dict(upstream_response.headers)
        response_headers.pop("content-encoding", None)
        response_headers.pop("transfer-encoding", None)

        return Response(
            content=response_content,
            status_code=upstream_response.status_code,
            headers=response_headers,
            media_type=upstream_response.headers.get("content-type", "application/json"),
        )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream LLM provider timed out")
    except Exception as e:
        logger.error("proxy_error", error=str(e))
        raise HTTPException(status_code=502, detail=f"Proxy error: {str(e)}")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "proxy"}