"""FastAPI application factory for the Industrial Knowledge Copilot."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from ..config import settings
from ..ingestion import IngestionPipeline
from ..models import DocType
from ..rag import Copilot, MaintenanceAgent, ComplianceAgent
from ..store import KnowledgeStore

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


# --------------------------------------------------------------------------- #
# Request / response schemas
# --------------------------------------------------------------------------- #
class QueryRequest(BaseModel):
    query: str = Field(..., min_length=2, description="Natural-language question")
    top_k: Optional[int] = Field(None, ge=1, le=20)
    doc_types: Optional[List[str]] = Field(None, description="Filter by document type values")


class IngestTextRequest(BaseModel):
    title: str
    text: str
    doc_type: str = DocType.OTHER.value
    metadata: dict = Field(default_factory=dict)


class DiagnoseRequest(BaseModel):
    equipment: str


class ComplianceRequest(BaseModel):
    topic: str


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #
def create_app(store: Optional[KnowledgeStore] = None) -> FastAPI:
    settings.ensure_dirs()
    store = store or KnowledgeStore.open()
    copilot = Copilot(store)

    app = FastAPI(
        title="Industrial Knowledge Copilot",
        version="1.0.0",
        description="RAG-powered conversational AI over heterogeneous industrial documents.",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
    )

    app.state.store = store
    app.state.copilot = copilot

    def _parse_doc_types(values: Optional[List[str]]) -> Optional[List[DocType]]:
        if not values:
            return None
        out = []
        for v in values:
            if v in DocType._value2member_map_:
                out.append(DocType(v))
            else:
                raise HTTPException(400, f"Unknown doc_type '{v}'")
        return out

    # ---- UI ----------------------------------------------------------------
    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        html = WEB_DIR / "index.html"
        if html.exists():
            return html.read_text(encoding="utf-8")
        return "<h1>Industrial Knowledge Copilot</h1><p>UI not found.</p>"

    # ---- Health & stats ----------------------------------------------------
    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": app.version, **store.stats()}

    @app.get("/api/documents")
    def documents() -> dict:
        return {"documents": store.list_documents()}

    @app.get("/api/doc_types")
    def doc_types() -> dict:
        return {"doc_types": [dt.value for dt in DocType]}

    # ---- Core query --------------------------------------------------------
    @app.post("/api/query")
    def query(req: QueryRequest) -> JSONResponse:
        dtypes = _parse_doc_types(req.doc_types)
        ans = copilot.answer(req.query, top_k=req.top_k, doc_types=dtypes)
        return JSONResponse(ans.to_dict())

    # ---- Ingestion ---------------------------------------------------------
    @app.post("/api/ingest/text")
    def ingest_text(req: IngestTextRequest) -> dict:
        dtype = DocType(req.doc_type) if req.doc_type in DocType._value2member_map_ else DocType.OTHER
        pipeline = IngestionPipeline(store)
        result = pipeline.ingest_text(req.title, req.text, doc_type=dtype, metadata=req.metadata)
        store.save()
        return result.to_dict()

    @app.post("/api/ingest/file")
    async def ingest_file(file: UploadFile = File(...), doc_type: str = Form(DocType.OTHER.value)) -> dict:
        suffix = Path(file.filename or "upload").suffix.lower()
        tmp = settings.data_dir / "_uploads"
        tmp.mkdir(parents=True, exist_ok=True)
        dest = tmp / (file.filename or "upload")
        dest.write_bytes(await file.read())
        pipeline = IngestionPipeline(store)
        result = pipeline.ingest_file(dest)
        store.save()
        return result.to_dict()

    # ---- Agentic workflows -------------------------------------------------
    @app.post("/api/agent/maintenance")
    def maintenance(req: DiagnoseRequest) -> dict:
        return MaintenanceAgent(store, copilot).diagnose(req.equipment).to_dict()

    @app.post("/api/agent/compliance")
    def compliance(req: ComplianceRequest) -> dict:
        return ComplianceAgent(store, copilot).check(req.topic).to_dict()
    
    # ---- Equipment graph -----------------------------------------------
    @app.get("/api/equipment/{tag}")
    def equipment(tag: str) -> dict:
        return copilot.equipment_brief(tag)

    return app


# Module-level app for `uvicorn iki.api.app:app`.
app = create_app()
