"""FastAPI routes: validate requests, then delegate to PolicyService."""

from contextlib import asynccontextmanager
from datetime import date
import json
import logging
from time import perf_counter
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from .config import Settings
from .errors import ServiceError
from .models import Analysis, Answer, Context, Question
from .providers import OllamaProvider
from .service import PolicyService
from .store import PolicyStore, load_policies
from .logging_config import configure_logging

log = logging.getLogger("policy_service")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def build_policy_service(settings, provider):
    """Read the PDF, open Chroma, and connect them to the business service."""
    policies = load_policies(settings.policy_file)
    log.info("Loaded %s policy records from %s", len(policies), settings.policy_file)
    store = PolicyStore(policies, provider, path=settings.chroma_path)
    return PolicyService(store, provider)


def create_app(settings=None, service=None):
    if not settings:
        settings = Settings.from_env()
    caller_json = settings.callers_file.read_text(encoding="utf-8")
    callers = json.loads(caller_json)
    identities = set()
    for caller in callers.values():
        tenant = caller["tenant"]
        role = caller["role"]
        identities.add((tenant, role))

    @asynccontextmanager
    async def lifespan(app):
        log_path = configure_logging()
        log.info("Service starting; log_file=%s", log_path)
        provider = None
        try:
            if service is None:
                provider = OllamaProvider(settings)

                # Read the policy PDF now; embeddings are built on the first search.
                app.state.service = build_policy_service(settings, provider)
            else:
                app.state.service = service
            log.info("Service ready; model=%s embedding_model=%s", settings.model, settings.embedding_model)
            # FastAPI serves requests while this function is paused at yield.
            yield
        except Exception:
            log.exception("Service lifecycle failed")
            raise
        finally:
            if provider:
                provider.close()
            log.info("Service stopped")

    app = FastAPI(title="Employee policy service", lifespan=lifespan)

    @app.middleware("http")
    async def log_request(request, call_next):
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            route = getattr(request.scope.get("route"), "path", "unmatched")
            log.exception("Request failed; method=%s route=%s", request.method, route)
            raise
        route = getattr(request.scope.get("route"), "path", "unmatched")
        elapsed_ms = (perf_counter() - started) * 1000
        log.info("Request completed; method=%s route=%s status=%s duration_ms=%.1f",
                 request.method, route, response.status_code, elapsed_ms)
        return response

    @app.exception_handler(ServiceError)
    async def failure(request, error):
        log.warning("Service error; code=%s status=%s", error.code, error.status)
        return JSONResponse(
            status_code=error.status,
            content={"code": error.code, "message": error.message},
        )

    def validate_context(context):
        caller_identity = (context.tenant, context.role)
        if caller_identity not in identities:
            raise ServiceError("INVALID_CONTEXT", "Unknown tenant and role context.", 400)

    # @app.get("/health")
    # def health():
    #     return {
    #         "status": "ok",
    #         "mode": "ollama",
    #         "model": settings.model,
    #         "note": "Liveness only; model availability is checked during processing.",
    #     }

    @app.post("/internal/answer", response_model=Answer)
    def answer(request: Question):
        validate_context(request)
        policy_service = app.state.service
        question_text = request.question
        result = policy_service.answer(request, question_text)
        return result

    @app.post("/internal/documents/analyze", response_model=Analysis)
    def analyze(
        tenant: str = Form(...),
        role: str = Form(...),
        as_of: date = Form(...),
        batch_id: str = Form(...),
        document_id: str = Form(...),
        file: UploadFile = File(...),
    ):
        context = Context(tenant=tenant, role=role, as_of=as_of)
        validate_context(context)
        if not batch_id.strip() or not document_id.strip():
            raise ServiceError("INVALID_REQUEST", "Batch and document IDs are required.", 400)
        try:
            content = file.file.read(MAX_UPLOAD_BYTES + 1)
            filename = file.filename or ""
            result = app.state.service.analyze(context, filename, content)
            log.info("batch=%r document=%r status=completed", batch_id, document_id)
            return result
        except ServiceError as exc:
            log.info("batch=%r document=%r status=failed code=%s", batch_id, document_id, exc.code)
            raise
        finally:
            file.file.close()

    return app


app = create_app()
