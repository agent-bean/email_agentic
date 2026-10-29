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
)

from email_agentic.models.reports import ReportEdit
from email_agentic.models.research import ResearchRequest
from email_agentic.platform.auth import Actor, authenticate
from email_agentic.runtime.jobs import enqueue

router = APIRouter(prefix="/api/v1", dependencies=[Depends(authenticate)])


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
            """SELECT d.id,d.report_id,d.status,d.provider_id,d.thread_id,d.error_code,
            (r.email_subject=latest.email_subject AND r.email_body=latest.email_body
             AND r.recipients=latest.recipients AND r.artifacts=latest.artifacts) AS matches_current
            FROM gmail_drafts d JOIN reports r ON r.id=d.report_id
            JOIN reports latest ON latest.run_id=d.run_id
             AND latest.version=(SELECT max(version) FROM reports WHERE run_id=d.run_id)
            WHERE d.run_id=%s ORDER BY d.created_at DESC""",
            (run_id,),
        ),
        "gmail_drafts_available": c.google.drafts_available,
    }


@router.post("/runs/{run_id}/identity", status_code=202)
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


@router.post("/approvals/{approval_id}/decision")
async def decide(
    approval_id: UUID, payload: Decision, request: Request, actor: Actor = Depends(authenticate)
):
    await request.app.state.container.approvals.decide(actor.owner, approval_id, payload.approve)
    return {"status": "approved" if payload.approve else "rejected"}


@router.get("/inputs")
async def inputs(request: Request, actor: Actor = Depends(authenticate)):
    rows = await request.app.state.container.db.all(
        """SELECT i.*,COALESCE(t.status,ct.status) AS intake_status,COALESCE(t.run_id,r.id,ct.run_id) AS research_run_id,ct.revision AS meeting_revision FROM inputs i
        LEFT JOIN email_triage t ON t.input_id=i.id AND t.owner=i.owner
        LEFT JOIN research_runs r ON r.source_input_id=i.id AND r.owner=i.owner
        LEFT JOIN LATERAL (SELECT status,run_id,revision FROM calendar_triage WHERE input_id=i.id AND owner=i.owner
         ORDER BY created_at DESC LIMIT 1) ct ON true
        WHERE i.owner=%s ORDER BY COALESCE((i.content->>'received_at')::timestamptz,i.created_at) DESC LIMIT 100""", (actor.owner,)
    )

    from email_agentic.integrations.calendar_event import revision
    for row in rows:
        if row['kind'] == 'meeting' and (row['calendar_available'] is False or row['meeting_revision'] != revision(row['content'])):
            row['research_run_id'], row['intake_status'] = None, 'superseded'
    return rows


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


@router.post("/runs/{run_id}/reports/{report_id}/exports/{format}", status_code=201)
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
    return await request.app.state.container.db.all(
        """SELECT p.id,r.run_id,r.version,r.email_subject,r.email_body,r.recipients,p.status,p.provider_id,
        p.error_code,a.created_at FROM publication_actions p JOIN approvals a ON a.id=p.approval_id
        JOIN reports r ON r.id=a.report_id WHERE r.owner=%s AND p.kind='email'
        ORDER BY a.created_at DESC LIMIT 100""", (actor.owner,))


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
