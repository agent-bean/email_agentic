# Architecture and Safety Boundaries

The [PRD](02_product-requirements.md) owns scope, schedules, retention policy, and acceptance criteria. This document owns design rationale and safety invariants. Executable fields, states, and endpoints belong to [migrations](../apps/backend/migrations/) and the [API](../apps/backend/src/email_agentic/api/routes.py).

## Design rationale

The web image permits independent interface releases; API and worker share an image because they share code and dependencies. A same-origin proxy provides one login route. Agent roles represent business responsibilities, not separate servers or mandatory model calls. Start with [bootstrap](../apps/backend/src/email_agentic/bootstrap.py), the [research workflow](../apps/backend/src/email_agentic/workflows/research.py), and [Compose](../infra/compose.yaml).

Code orchestration keeps ordering, deadlines, and human checkpoints explicit. Add a supervisor, microservices, MCP/A2A, Redis/Celery, or a broker only for a demonstrated need. PostgreSQL holds business data, jobs, and checkpoints to avoid separate queue infrastructure at this scale. These records have different authority: business data determines approval and publication outcomes; checkpoints support continuation.

[Domains](../apps/backend/src/email_agentic/domains/) own transactions and business rules; agents interpret content, tools own privileged operations, and integrations connect providers. Only the business owner changes its data. Memory and KB retrieval begin with PostgreSQL; course examples alone do not justify a vector database or GraphRAG. Approved KB content differs from draft memory, and LangGraph Store must not become a second authoritative KB.

[Shared models](../apps/backend/src/email_agentic/models/) define contracts across these boundaries. They must not perform I/O or replace domain transaction rules. Parameterized SQL and migrations remain the persistence boundary; a models package alone is not a reason to introduce an ORM.

## Identity, sources, and content

Do not merge legal entities by display name, personal email, or parent/subsidiary relationships. Confirming company identity is separate from approving publication. Email, calendar, PDF, and web content are untrusted data; they cannot grant permissions or override instructions. Give agents only necessary context. Keep chain-of-thought and secrets out of prompts, checkpoints, audits, and telemetry.

Preserve the source email separately from research instructions. Fetch Google snapshots under the backend's owner identity rather than trusting client metadata. Calendar input has independent provenance and requires version, change, and cancellation checks. Owners: [research service](../apps/backend/src/email_agentic/domains/research/service.py), [Gmail sync](../apps/backend/src/email_agentic/domains/inbox/sync.py), and [calendar automation](../apps/backend/src/email_agentic/domains/inbox/calendar.py).

Only confirmed company/domain identity belongs in public search. Do not disclose private email, calendar, or PDF content to search/scrape providers. Retrieved pages and snippets are not verified facts. Collection dates do not replace publication dates; distinguish historical context, contradictions, and missing information. Potential needs are evidence-based inferences. [Web research](../apps/backend/src/email_agentic/agents/web_research.py) and [report generation](../apps/backend/src/email_agentic/agents/report_generation.py) own collection, prompts, and citations.

Internal reports and customer emails serve different audiences. Customer content must not expose internal assessments or private third-party information, or invent capabilities and commitments. Keep evaluation provenance in metadata rather than customer-facing prose.

## What approval protects

Approval binds the exact content version, To/Cc/Bcc recipients, files, and send/store choices. Changing approved material requires a new version and decision. Do not call a model to rewrite content after approval. Preserve attachment bytes and checksums; downloading a file does not authorize attaching it. Owners: [approvals](../apps/backend/src/email_agentic/domains/approvals/service.py), [reports](../apps/backend/src/email_agentic/domains/reports/), and [publication](../apps/backend/src/email_agentic/domains/publication/).

Persist the decision and publication work atomically. A checkpoint, resume payload, or frontend boolean is not approval evidence. Superseding a package must block obsolete actions that have not started. Once a send request has begun, do not promise recall; preserve the actual result even if the user makes later edits.

Gmail Draft export does not authorize sending or KB storage. Drafts can change externally, so sending requires content, thread, and attachment reconciliation. A missing or changed draft is not permission to send a new email instead. Ambiguous delivery requires reconciliation rather than blind retries. Message-ID supports lookup but does not guarantee Gmail deduplication. A KB failure after successful delivery must not trigger another send. Owners: publication and the [Google integration](../apps/backend/src/email_agentic/integrations/google.py).

## Tools, permissions, and recovery

The [tool harness](../apps/backend/src/email_agentic/tools/harness.py) owns the PRD gate sequence, including worker/scheduler calls. Runtime supplies identity, owner, and role; general permission cannot replace package approval. Send and KB tools belong to the runtime after approval, outside the LLM allowlist. Audit failure must block execution. Business audit evidence is separate from sampled traces.

Jobs need deduplication and leases. Do not hold database transactions across network calls or human waits. Database and checkpoint commits are not automatically atomic; replay requires locking and reconciliation. An expired lease cannot recall a Gmail request already sent over the network. Retries share a budget rather than multiplying across SDK, node, and worker layers. Owners: [runtime](../apps/backend/src/email_agentic/runtime/), [worker](../apps/backend/src/email_agentic/worker.py), and research workflow.

Cloudflare Access does not replace ownership, version, Origin, or approval checks. Google OAuth connects the mailbox/calendar and is distinct from application login. Parsing/export must stay bounded and must not fetch arbitrary resources from model content. Owners: [auth](../apps/backend/src/email_agentic/platform/auth.py), [report files](../apps/backend/src/email_agentic/domains/reports/files.py), and [renderer](../apps/backend/src/email_agentic/integrations/report_export.py).

Do not delete data still needed for pending work or send reconciliation. [Retention](../apps/backend/src/email_agentic/platform/retention.py) owns cleanup; [operations](06_release-and-operations.md) owns backup/restore. Traces cannot prove permission or approval. Unknown provider prices remain unknown rather than being treated as zero.

## Verification boundaries

Use [backend tests](../apps/backend/tests/) for ownership, concurrent edits/approvals, expiry, restart, leases, uncertain delivery, KB failure after sending, and file access. For changed public contracts, select web checks through the [contribution guide](08_contributing-and-quality.md). Live integration evidence and [product evaluation](05_evaluation-guide.md) answer different questions: passing tests alone proves neither briefing quality nor authorization to expand production data access.
