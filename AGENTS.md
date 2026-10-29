# Agent Working Rules

## Changes and coordination

- Always delegate independent, clearly scoped tasks to subagents. Give each delegate exact read/write boundaries, acceptance criteria, constraints, and the selected skill. Parallelize only disjoint ownership; keep shared DB/process control and final integration with the controller.
- Reuse shared Pydantic contracts in `apps/backend/src/email_agentic/models/`; add models for meaningful validation boundaries, not empty wrappers. Preserve compatibility exports and public contracts unless the requested change explicitly replaces them. Keep I/O and transaction rules out of models.
- Organize backend tests by layer and module under `apps/backend/tests/{unit,integration,e2e}/<module>/`. Keep web tests in their existing layer directories. Prove rules with unit tests, real database/module contracts with integration tests, and critical public journeys with E2E tests; do not duplicate coverage across layers without a distinct risk.
- Write documentation in English, except `docs/02_product-requirements.md`, whose Vietnamese language must be preserved. Start at [the documentation index](docs/01_index.md); keep run evidence in `plans/reports/` rather than evergreen guides.

## Data and operations

- Back up the target database before manual writes, migrations, restores, or destructive test preparation; stop if backup fails. Use the guarded local test commands below instead of bypassing preparation.
- Do not run a local worker against the same mailbox concurrently with the VPS worker, even when they use separate databases. `make up` is a local stack command, not a production deployment command.
- Use isolated test databases and provider doubles at external boundaries; never call production providers or load production credentials/data in tests. Preserve real persistence and browser coverage where those contracts are under test.
- Never put secret values in prompts, reports, Git, PRs, or public artifacts. Keep golden answers out of runtime and generation prompts. Use raw email and private fixtures only within authorized processing or protected evaluation; keep them and private operations documents out of Git and public artifacts. Preserve `.gitignore` protections; never read secrets just to document their location.
- Check existing processes and ports before starting a server or worker. Track and stop processes you start; do not stop another session's processes or evade a busy port by starting duplicates.
- Use [the operations guide](docs/06_release-and-operations.md) for deployment, backup, rollback, and restricted operational lookup routes.

## Verification and delivery

Run commands from the repository root. Start with the narrowest relevant check:

- Backend unit module: `uv run --project apps/backend pytest apps/backend/tests/unit/models -q` (replace `models` with the affected module).
- Backend database tests: `make test PYTEST_ARGS='-m integration -k publication'` (select the affected marker/module); first follow the local database prerequisites in [the application guide](docs/03_application-guide.md).
- Web unit/component tests: `npm run test:unit --prefix apps/web` or `npm run test:integration --prefix apps/web`; use `make web-test` when browser coverage with a prepared test database is needed.
- Operational scripts: `make test-scripts`. Backend changes: `make lint`. Web changes: `make typecheck web-build`.

Run local tests sequentially unless safe parallelism is established. Broaden checks when shared contracts change; do not run expensive suites without a relevant risk. Fix or report every observed failure and distinguish skipped checks from passes.

Deliver through a feature branch, Conventional Commit PR title, passing `verify`, and squash merge; never push directly to `main`. Follow [the contribution guide](docs/08_contributing-and-quality.md) and the CI workflow's required gates. Inspect the staged diff for private data before committing. Report the actual checks and remaining limits; passing CI does not establish PRD acceptance or authorize production actions.
