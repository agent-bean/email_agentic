from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from email_agentic.domains.reports.service import ReportEdit
from email_agentic.domains.research.service import ResearchRequest
from email_agentic.platform.auth import Actor, authenticate
from email_agentic.runtime.jobs import enqueue

router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])


class RunSummary(BaseModel):
    id: UUID
    company_name: str
    domain: str
    context: str
    status: str
    version: int
    created_at: datetime
    elapsed_seconds: float | None
    error_code: str | None
    config: dict


class RunRecord(RunSummary):
    source_email: str | None = None
    source_input_id: UUID | None = None
    source_message: dict | None = None


class ReportRow(BaseModel):
    id: UUID
    run_id: UUID
    version: int
    markdown: str
    email_subject: str
    email_body: str
    recipients: dict[str, list[str]]
    send_email: bool
    save_kb: bool
    quality: dict
    artifacts: list[dict]


class ApprovalRow(BaseModel):
    id: UUID
    report_id: UUID
    status: str
    expires_at: datetime


class ActionRow(BaseModel):
    id: UUID
    kind: str
    status: str
    provider_id: str | None
    error_code: str | None


class RunDetail(BaseModel):
    run: RunRecord
    reports: list[ReportRow]
    approvals: list[ApprovalRow]
    actions: list[ActionRow]
    branches: list[dict]
    evidence: list[dict]
    usage: list[dict]
    gmail_drafts: list[dict]
    gmail_drafts_available: bool


class Created(BaseModel):
    id: UUID


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approve: bool


class IdentityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)


@router.get("/me")
async def me(actor: Actor = Depends(authenticate)):
    return {"email": actor.owner, "role": actor.role}


@router.get("/runs", response_model=list[RunSummary])
async def runs(request: Request, actor: Actor = Depends(authenticate)):
    return await request.app.state.container.db.all(
        "SELECT * FROM research_runs WHERE owner=%s ORDER BY created_at DESC LIMIT 100", (actor.owner,)
    )


@router.post("/runs", status_code=202, response_model=Created)
async def create_run(
    payload: ResearchRequest,
    request: Request,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(min_length=8, max_length=100),
):
    return {"id": await request.app.state.container.research.create(actor.owner, payload, idempotency_key)}


@router.get("/runs/{run_id}", response_model=RunDetail)
async def run_detail(run_id: UUID, request: Request, actor: Actor = Depends(authenticate)):
    c = request.app.state.container
    run = await c.research.get(actor.owner, run_id)
    reports = await c.db.all("SELECT * FROM reports WHERE run_id=%s ORDER BY version DESC LIMIT 1", (run_id,))
    approvals = await c.db.all(
        "SELECT * FROM approvals WHERE report_id IN(SELECT id FROM reports WHERE run_id=%s) ORDER BY created_at DESC",
        (run_id,),
    )
    actions = await c.db.all(
        "SELECT * FROM publication_actions WHERE approval_id IN(SELECT a.id FROM approvals a JOIN reports r ON r.id=a.report_id WHERE r.run_id=%s)",
        (run_id,),
    )
    return {
        "run": run,
        "reports": reports,
        "approvals": approvals,
        "actions": actions,
        "branches": await c.db.all("SELECT * FROM branch_results WHERE run_id=%s", (run_id,)),
        "evidence": await c.db.all(
            "SELECT id,url,title,published_at FROM evidence WHERE run_id=%s", (run_id,)
        ),
        "usage": await c.db.all(
            "SELECT model,input_tokens,output_tokens,cost FROM model_usage WHERE run_id=%s", (run_id,)
        ),
        "gmail_drafts": await c.db.all(
            "SELECT id,report_id,status,provider_id,thread_id,error_code FROM gmail_drafts WHERE run_id=%s ORDER BY created_at DESC",
            (run_id,),
        ),
        "gmail_drafts_available": c.google.drafts_available,
    }


@router.post("/runs/{run_id}/identity", status_code=202)
async def identity(
    run_id: UUID, payload: IdentityDecision, request: Request, actor: Actor = Depends(authenticate)
):
    await request.app.state.container.approvals.confirm_identity(actor.owner, run_id, payload.version)
    return {"status": "queued"}


@router.put("/runs/{run_id}/report", response_model=Created)
async def edit_report(
    run_id: UUID, payload: ReportEdit, request: Request, actor: Actor = Depends(authenticate)
):
    return {"id": await request.app.state.container.reports.edit(actor.owner, run_id, payload)}


@router.post("/approvals/{approval_id}/decision")
async def decide(
    approval_id: UUID, payload: Decision, request: Request, actor: Actor = Depends(authenticate)
):
    await request.app.state.container.approvals.decide(actor.owner, approval_id, payload.approve)
    return {"status": "approved" if payload.approve else "rejected"}


@router.get("/inputs")
async def inputs(request: Request, actor: Actor = Depends(authenticate)):
    return await request.app.state.container.db.all(
        "SELECT * FROM inputs WHERE owner=%s ORDER BY COALESCE((content->>'received_at')::timestamptz,created_at) DESC LIMIT 100", (actor.owner,)
    )


@router.get("/inputs/{input_id}")
async def input_detail(input_id: UUID, request: Request, actor: Actor = Depends(authenticate)):
    from email_agentic.platform.errors import NotFound

    row = await request.app.state.container.db.one("SELECT * FROM inputs WHERE id=%s AND owner=%s",
                                                (input_id, actor.owner))
    if not row:
        raise NotFound()
    return row


@router.post("/runs/{run_id}/gmail-draft", status_code=202, response_model=Created)
async def gmail_draft(run_id: UUID, payload: IdentityDecision, request: Request, actor: Actor = Depends(authenticate)):
    from email_agentic.platform.errors import Conflict

    if not request.app.state.container.google.drafts_available:
        raise Conflict("Cần kết nối Google với quyền gmail.compose để lưu Gmail Drafts")
    return {"id": await request.app.state.container.drafts.request(actor.owner, run_id, payload.version)}


@router.get("/knowledge")
async def knowledge(request: Request, actor: Actor = Depends(authenticate)):
    return await request.app.state.container.db.all(
        "SELECT * FROM knowledge WHERE owner=%s ORDER BY created_at DESC LIMIT 100", (actor.owner,)
    )


@router.get("/companies")
async def companies(request: Request, actor: Actor = Depends(authenticate)):
    return await request.app.state.container.db.all(
        "SELECT * FROM companies WHERE owner=%s ORDER BY created_at DESC LIMIT 100", (actor.owner,)
    )


@router.get("/system")
async def system(request: Request):
    c = request.app.state.container
    return {
        "mode": c.settings.environment,
        "model": c.settings.llm_model,
        "target_seconds": c.settings.report_target_seconds,
        "scheduler_enabled": c.settings.scheduler_enabled,
        "connections": {
            "llm": "configured" if c.settings.llm_api_key.get_secret_value() else "missing",
            "tavily": "configured" if c.settings.tavily_api_key.get_secret_value() else "missing",
            "duckduckgo": "configured" if c.settings.duckduckgo_enabled else "disabled",
            "firecrawl": "configured" if c.settings.firecrawl_api_key.get_secret_value() else "missing",
            "google": "configured" if c.settings.google_token_path.exists() else "missing",
            "google_drafts": "configured" if c.google.drafts_available else "requires_consent",
        },
        "jobs": await c.db.all("SELECT kind,status,count(*) AS total FROM jobs GROUP BY kind,status"),
    }


@router.post("/sync/{provider}", status_code=202)
async def sync(
    provider: str,
    request: Request,
    actor: Actor = Depends(authenticate),
    idempotency_key: str = Header(min_length=8, max_length=100),
):
    kind = {"email": "scan_email", "calendar": "scan_calendar"}.get(provider)
    if not kind:
        raise HTTPException(404, "Unknown source")
    async with request.app.state.container.db.transaction() as connection:
        await enqueue(
            connection, actor.owner, kind, None, f"manual-sync:{actor.owner}:{provider}:{idempotency_key}"
        )
    return {"status": "queued"}
