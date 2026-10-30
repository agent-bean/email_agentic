# Contributing and quality verification

Use a work branch → pull request → successful CI → squash merge → CI on `main` → deployment of that exact commit. Do not push directly to `main`. The [workflow](../.github/workflows/ci-cd.yml) owns verification commands and deployment conditions; [operations](06_release-and-operations.md) owns backup, rollback, and production permissions.

## Branches, commits, and pull requests

Start from current `main` and name branches `<type>/<short-description>`, such as `feat/review-workspace` or `fix/approval-expiry`. The [convention checker](../scripts/check-pr-conventions.py) owns accepted types. Use Conventional Commits for commits and PR titles, for example `feat(web): improve report review`. Scope is optional; explain contract and migration effects for breaking changes. Keep commits focused, with no AI references or phase/audit labels in code or commit messages.

```bash
git fetch origin
git switch -c feat/review-workspace origin/main
make hooks-install
# Edit, test, review the diff, and commit only in-scope files.
git push -u origin feat/review-workspace
gh pr create --base main --title 'feat(web): improve report review' --body-file /path/to/pr-body.txt
```

`make hooks-install` is an optional local guard against pushes targeting `main`, including pushes from differently named source branches. The [installer](../scripts/install-git-hooks.py) refuses to replace existing hooks/configuration; integrate the guard manually in that case. Hooks do not replace GitHub protection because `--no-verify` can bypass them.

Describe the concrete problem and resulting behavior in the PR, then provide affected contracts/migrations, actual validation results and unrun checks with reasons, risks and rollback, and before/after images when the UI changes. Never include email, user data, tokens, dotenv files, private fixtures, production logs, or screenshots containing real data in PRs or artifacts. Inspect `git diff --cached` before committing.

Review correctness, ownership, approval, retries, and migration impact. Passing tests does not replace product acceptance. Squash merge only after `verify` passes and review conversations are resolved. A single-owner repository does not require an unavailable second reviewer.

## Test layers and module ownership

For agent work, the controller delegates clearly bounded tasks with goals, readable/editable files, acceptance criteria, and the selected relevant skill. Parallel work requires disjoint ownership: agents must not edit the same file/configuration or control the same database/process. The controller owns integration decisions, diff review, cross-module verification, and final reporting. Delegates must not expand scope or revert another contributor's changes.

[EditorConfig](../.editorconfig) owns formatting conventions. [Backend configuration](../apps/backend/pyproject.toml), [web scripts](../apps/web/package.json), and the CI workflow own lint/type/build checks. Update lockfiles with dependency changes; CI uses frozen/clean installs.

Declare response models for JSON endpoints and consume generated operation types in the web client. After a contract change, run `make api-generate` and include the generated diff; `make api-check` fails CI when source and generated types differ. Keep explicit tests for version conflicts, unsaved navigation, stale lease outcomes, recovery, and rendering/retention races when changing those boundaries.

Use unit tests for isolated rules, integration tests for real database/renderer/process contracts, and E2E for public API and persistence journeys. Backend test layers live under `apps/backend/tests/{unit,integration,e2e}/<module>/`; web tests separate unit, component integration, and browser E2E with a real backend/database. Provider doubles belong at test boundaries, never in runtime implementation. CI must not call production providers.

Run the narrowest useful layer first. The [Makefile](../Makefile) owns root commands (`make help` lists them), including `test-unit`, `test-integration`, `test-e2e`, `test`, `test-scripts`, `web-test`, `lint`, and `web-build`. Filter backend tests with `PYTEST_ARGS`, for example `make test PYTEST_ARGS='-m integration -k publication'`. The web package owns direct npm test commands; the workflow is the authoritative full CI sequence.

Run `make setup` for dependencies. For local backend integration/E2E, prepare Docker and local configuration following the [application guide](03_application-guide.md), then run `make db build`. The [local helper](../scripts/app-control.py) owns backup/migration and creation of the separate `email_agentic_test` database. Never point tests at production. CI requires its isolated PostgreSQL service with `--require-database`, so missing databases fail instead of skipping required layers. Backend unit tests do not need PostgreSQL.

After `make db build`, use `make web-test` for the web layers. It shares the helper's backup and isolated-database preparation and passes `TEST_DATABASE_URL` without printing credentials. Backup/migration failure must stop E2E. Direct npm E2E is for CI or an already prepared test database and requires an explicit `TEST_DATABASE_URL`.

Install Chromium once with `cd apps/web && npx --no-install playwright install --with-deps chromium`. The [browser runner](../apps/web/playwright.config.ts) manages its API/Vite test servers. Stop processes you start when work ends; do not create duplicates. CI installs the browser through the locked Playwright dependency rather than implicitly downloading a different package. Never upload traces or logs containing sensitive data.

## GitHub main protection

The [branch-protection declaration](../.github/main-protection.json) owns required checks, review/conversation requirements, history constraints, and administrator enforcement. The [repository settings](../.github/repository-settings.json) own squash-only merging, PR-title commit naming, and branch deletion after merge. These files express desired configuration; their existence does not prove remote enforcement. Audit by reading current GitHub settings. Each clone needs its own optional hook installation.

An administrator reviews these declarations and applies them only with authorization:

```bash
gh api --method PUT repos/agent-bean/email_agentic/branches/main/protection --input .github/main-protection.json
gh api repos/agent-bean/email_agentic/branches/main/protection
gh api --method PATCH repos/agent-bean/email_agentic --input .github/repository-settings.json
gh api repos/agent-bean/email_agentic
```

The `verify` check name is a branch-protection contract; update the declaration when renaming the job. Squash merging preserves the PR title as the main commit title and satisfies linear history. Branch protection does not replace environment `vps` permissions or secret management. Workflow and production entry-point changes require review against the operations guide's permission boundaries. Store application receipts and protected pre-change configuration in operational evidence, not this evergreen guide.
