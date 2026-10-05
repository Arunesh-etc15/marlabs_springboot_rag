"""FastAPI routes: validate requests, then delegate to PolicyService."""

from contextlib import asynccontextmanager
from datetime import date
import json
import logging
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse
from .config import Settings
from .errors import ServiceError
from .models import Analysis, Answer, Context, Question
from .providers import OfflineProvider, OllamaProvider
from .service import PolicyService
from .store import PolicyStore, load_policies

log = logging.getLogger("policy_service")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def create_app(settings=None, service=None):
    settings = settings or Settings.from_env()
    caller_json = settings.callers_file.read_text(encoding="utf-8")
    callers = json.loads(caller_json)
    identities = set()
    for caller in callers.values():
        identities.add((caller["tenant"], caller["role"]))

    @asynccontextmanager
    async def lifespan(app):
        provider = None
        if service is None:
            if settings.mode == "offline":
                provider = OfflineProvider()
            else:
                provider = OllamaProvider(settings)

            # Read the policy PDF now; embeddings are built on the first search.
            policies = load_policies(settings.policy_file)
            log.info("Loaded %s policy records from %s", len(policies), settings.policy_file)
            store = PolicyStore(policies, provider, path=settings.chroma_path)
            app.state.service = PolicyService(store, provider)
        else:
            app.state.service = service
        try:
            yield
        finally:
            if provider:
                provider.close()

    app = FastAPI(title="Employee policy service", lifespan=lifespan)

    @app.exception_handler(ServiceError)
    async def failure(request, error):
        return JSONResponse(
            status_code=error.status,
            content={"code": error.code, "message": error.message},
        )

    def validate_context(context):
        if (context.tenant, context.role) not in identities:
            raise ServiceError("INVALID_CONTEXT", "Unknown tenant and role context.", 400)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "mode": settings.mode,
            "model": settings.model,
            "note": "Liveness only; model availability is checked during processing.",
        }

    @app.post("/internal/answer", response_model=Answer)
    def answer(request: Question):
        validate_context(request)
        return app.state.service.answer(request, request.question)

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
            result = app.state.service.analyze(context, file.filename or "", content)
            log.info("batch=%r document=%r status=completed", batch_id, document_id)
            return result
        except ServiceError as exc:
            log.info("batch=%r document=%r status=failed code=%s", batch_id, document_id, exc.code)
            raise
        finally:
            file.file.close()

    return app


app = create_app()
