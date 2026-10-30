# Application and Local Development

Start with the [product requirements](02_product-requirements.md) for the intended outcome and [architecture and safety](04_architecture-and-safety.md) for constraints on changes. Run evidence belongs in `plans/reports/`; it does not establish that every acceptance criterion has passed.

## Local setup

Use Python/uv, Node/npm, and Docker Compose. Dependency requirements belong to the [backend manifest](../apps/backend/pyproject.toml), [web manifest](../apps/web/package.json), and their lockfiles. Configure from [.env.example](../.env.example); never commit credentials or print resolved configuration.

Run `make help` at the repository root for the command catalog in the [Makefile](../Makefile). For initial setup, follow `setup`, `check`, `db`, `build`, `migrate`, then `up`. A successful backup must precede schema changes. The [local helper](../scripts/app-control.py) owns execution and [local Compose](../infra/compose.local.yaml) owns addresses and ports. Production follows the [release guide](06_release-and-operations.md).

Do not run a local worker against the production mailbox and a copied production database: independent databases cannot prevent each other's duplicate sends. Do not repeat seeding against the prepared Google dataset. Mount runtime tokens read-only for the required container user; keep seed tokens out of runtime. Do not delete volumes to fix routine startup failures.

Use the [contribution guide](08_contributing-and-quality.md) to choose checks appropriate to the change. The database-backed test helper requires local PostgreSQL and the backend image; unit tests have a separate route. Stop only processes you started or are authorized to manage. The Makefile owns stack status and shutdown commands, including shutdown that preserves volumes.

## Operator workspace

The interface defaults to Vietnamese. The sidebar language selector switches all interface guidance and controls between Vietnamese and English and remembers the choice in this browser. Customer messages, reports, generated drafts, and diagnostic details retain their original content.

Incoming email and meetings have separate navigation and filters. Open a source to read its content before creating research. Email sending history distinguishes requests from confirmed delivery; checking Gmail is an explicit read-only action, and a search miss does not establish that delivery failed. The knowledge library offers search, status filters, pagination, and one report reader at a time. Search covers the newest 100 records returned by the API; it is not a complete archive search.

The report editor retains unsaved changes when another tab saves a newer version. A conflict blocks overwriting that version and offers explicit reload after copying any changes to keep. Leaving the research page, including browser Back, requires discarding unsaved changes explicitly. If source retention makes the report read-only while editing, the unsaved draft remains available to copy in the current page but cannot be saved. Drafts are held in page memory, not browser storage; discarding them or closing the page loses them. Active runs/publications refresh frequently; completed records refresh less often.

## Review and publication decisions

- Preserve the customer's original email separately from research instructions. Do not reconstruct it from old context. Calendar and attachment inputs retain their own provenance.
- Confirm the legal entity and domain before research. Identity confirmation does not authorize sending, report publication, or KB storage.
- Review the internal report and customer email separately. Check sources, gaps, contradictions, and inferred needs; having a draft does not establish quality.
- Review recipients, body, attachments, and publication choices as one version. Downloading a report does not select it for sending. An expired proposal requires a new edited version before another proposal.
- Exporting to Gmail Drafts requires compose scope and grants no approval to send or write to the KB. Reconcile external draft edits, and avoid sending the same content through both Gmail and the application.
- If delivery is uncertain, reconcile with Sent before deciding whether to send again. An immediate search miss does not prove that nothing was sent.

New automation needs a cutoff to avoid processing historical mail in bulk. [Settings](../apps/backend/src/email_agentic/platform/config.py) owns configuration and defaults; the private operations guide owns activation in the real environment.

## Find the implementation owner

| Change | Owner |
| --- | --- |
| Interface and navigation | [Web app](../apps/web/src/app/app.tsx), [features](../apps/web/src/features/) |
| HTTP and authorization | [API](../apps/backend/src/email_agentic/api/routes.py), [auth](../apps/backend/src/email_agentic/platform/auth.py) |
| Shared contracts | [Models](../apps/backend/src/email_agentic/models/) |
| Startup and background work | [Bootstrap](../apps/backend/src/email_agentic/bootstrap.py), [worker](../apps/backend/src/email_agentic/worker.py) |
| Research and content | [Workflow](../apps/backend/src/email_agentic/workflows/research.py), [agents](../apps/backend/src/email_agentic/agents/) |
| Business rules and persistence | [Domains](../apps/backend/src/email_agentic/domains/), [migrations](../apps/backend/migrations/) |
| Providers and authorized tools | [Integrations](../apps/backend/src/email_agentic/integrations/), [harness](../apps/backend/src/email_agentic/tools/harness.py) |

For HTTP contract changes, run `make api-generate` (or `api:generate` in the web manifest) to regenerate [web types](../apps/web/src/lib/api-schema.ts) from OpenAPI. The [generator](../scripts/check-api-contract.py) uses declared settings defaults without loading credentials, starting a server, or connecting to a database. Run `make api-check` to detect drift. Do not edit generated types by hand. Separate web and backend releases require compatible API contracts.

## Interpreting limitations

A processing timeout is not a performance target; increasing it does not demonstrate PRD compliance. The [evaluation guide](05_evaluation-guide.md) owns acceptance interpretation. One successful run, an approved package, or a URL count does not establish overall quality.

Sources may be missing, stale, or blocked. A collected citation does not prove a fact. PDF/OCR failures and unread pages require review. Execution limits belong to [web research](../apps/backend/src/email_agentic/agents/web_research.py), integrations, and Settings.

[Retention](../apps/backend/src/email_agentic/platform/retention.py) owns cleanup and protection of pending work. Expired sources reduce reproducibility; an old snapshot is not automatically current evidence. Application cleanup does not delete Google mail or calendar events. Backups have a separate lifecycle in the [operations guide](06_release-and-operations.md).
