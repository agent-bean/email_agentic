import asyncio
from uuid import UUID

from fastapi.responses import Response
from fastapi import APIRouter, Depends, Header, HTTPException, Request

from email_agentic.models.api import (
    RunSummary as RunSummary,
    RunRecord as RunRecord,
    ReportRow as ReportRow,
    ApprovalRow as ApprovalRow,
    ActionRow as ActionRow,
    RunDetail as RunDetail,
    Created as Created,
    Decision as Decision,
    IdentityDecision as IdentityDecision,
    IdentityConfirmation as IdentityConfirmation,
    SentReviewRow as SentReviewRow,
    SentVerification as SentVerification,
    CompanyRow, KnowledgeRow, SystemStatus, CurrentUser, Queued, DecisionResult,
)

from email_agentic.models.reports import ReportEdit, AttachmentDescriptor
from email_agentic.models.sources import SourceInput
from email_agentic.api.queries import WorkspaceQueries
from email_agentic.models.research import ResearchRequest
from email_agentic.platform.auth import Actor, authenticate
from email_agentic.runtime.jobs import enqueue

router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])


@router.get("/me", response_model=CurrentUser)
async def me(actor: Actor = Depends(authenticate)):
    return {"email": actor.owner, "role": actor.role}


@router.get("/runs", response_model=list[RunSummary])
async def runs(request: Request, actor: Actor = Depends(authenticate)):
    return await WorkspaceQueries(request.app.state.container.db).runs(actor.owner)


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
    return await WorkspaceQueries(request.app.state.container.db).run_detail(actor.owner, run_id, request.app.state.container.google.drafts_available)


@router.post("/runs/{run_id}/identity", status_code=202, response_model=Queued)
async def identity(
    run_id: UUID, payload: IdentityConfirmation, request: Request, actor: Actor = Depends(authenticate)
):
    await request.app.state.container.approvals.confirm_identity(
        actor.owner, run_id, payload.version, payload.company_name, payload.domain
    )
    return {"status": "queued"}


@router.put("/runs/{run_id}/report", response_model=Created)
async def edit_report(
    run_id: UUID, payload: ReportEdit, request: Request, actor: Actor = Depends(authenticate)
):
    return {"id": await request.app.state.container.reports.edit(actor.owner, run_id, payload)}


@router.post("/approvals/{approval_id}/decision", response_model=DecisionResult)
async def decide(
    approval_id: UUID, payload: Decision, request: Request, actor: Actor = Depends(authenticate)
):
    await request.app.state.container.approvals.decide(actor.owner, approval_id, payload.approve)
    return {"status": "approved" if payload.approve else "rejected"}


@router.get("/inputs", response_model=list[SourceInput])
async def inputs(request: Request, actor: Actor = Depends(authenticate)):
    return await WorkspaceQueries(request.app.state.container.db).inputs(actor.owner)


@router.get("/inputs/{input_id}", response_model=SourceInput)
async def input_detail(input_id: UUID, request: Request, actor: Actor = Depends(authenticate)):
    return await WorkspaceQueries(request.app.state.container.db).input_detail(actor.owner, input_id)


@router.post("/runs/{run_id}/gmail-draft", status_code=202, response_model=Created)
async def gmail_draft(run_id: UUID, payload: IdentityDecision, request: Request, actor: Actor = Depends(authenticate)):
    from email_agentic.platform.errors import Conflict

    if not request.app.state.container.google.drafts_available:
        raise Conflict("Cần kết nối Google với quyền gmail.compose để lưu Gmail Drafts")
    return {"id": await request.app.state.container.drafts.request(actor.owner, run_id, payload.version)}


@router.get("/knowledge", response_model=list[KnowledgeRow])
async def knowledge(request: Request, actor: Actor = Depends(authenticate)):
    return await WorkspaceQueries(request.app.state.container.db).knowledge(actor.owner)


@router.get("/companies", response_model=list[CompanyRow])
async def companies(request: Request, actor: Actor = Depends(authenticate)):
    return await WorkspaceQueries(request.app.state.container.db).companies(actor.owner)


@router.get("/system", response_model=SystemStatus)
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


@router.post("/sync/{provider}", status_code=202, response_model=Queued)
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


@router.post("/runs/{run_id}/reports/{report_id}/exports/{format}", status_code=201, response_model=AttachmentDescriptor)
async def export_report(run_id: UUID, report_id: UUID, format: str, request: Request, actor: Actor = Depends(authenticate)):
    return await request.app.state.container.reports.files.export(actor.owner, run_id, report_id, format)


@router.get("/files/{file_id}")
async def download_file(file_id: UUID, request: Request, inline: bool = False, actor: Actor = Depends(authenticate)):
    row = await request.app.state.container.reports.files.get(actor.owner, file_id)
    return Response(content=bytes(row['data']), media_type=row['mime_type'], headers={
        'Content-Disposition': f'{"inline" if inline and row["format"] == "pdf" else "attachment"}; filename="{row["filename"]}"', 'Cache-Control': 'private, no-store',
        'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "sandbox; default-src 'none'"})


@router.get("/sent-review", response_model=list[SentReviewRow])
async def sent_review(request: Request, response: Response, actor: Actor = Depends(authenticate)):
    response.headers['Cache-Control'] = 'private, no-store'
    return await WorkspaceQueries(request.app.state.container.db).sent_review(actor.owner)


@router.get("/sent-review/{action_id}", response_model=SentVerification)
async def verify_sent(action_id: UUID, request: Request, response: Response, actor: Actor = Depends(authenticate)):
    from email_agentic.platform.errors import ProviderFailure

    response.headers['Cache-Control'] = 'private, no-store'
    c = request.app.state.container
    try:
        async with asyncio.timeout(30):
            return await c.publication.sent_review(actor.owner, action_id, c.google)
    except (ProviderFailure, TimeoutError):
        raise HTTPException(502, "Chưa đối chiếu được Gmail Sent. Kiểm tra kết nối/quyền đọc Gmail rồi thử lại.") from None
