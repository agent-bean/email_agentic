# Email Assistant Documentation

## Getting started

1. [Product requirements](02_product-requirements.md): agreed goals, scope, and acceptance criteria; maintained in Vietnamese.
2. [Application and local development](03_application-guide.md): setup, usage, and source navigation.
3. [Architecture and safety](04_architecture-and-safety.md): design rationale, permissions, and invariants to preserve when changing code.

## Maintenance

- [Evaluation](05_evaluation-guide.md): inputs, golden answers, review, regression checks, and acceptance.
- [Release and operations](06_release-and-operations.md): CI, deployment, backup, retention, and rollback.
- [Contributing and quality](08_contributing-and-quality.md): branches, PRs, conventions, test layers, and `main` protection.
- Private guide at `docs/07_private-operations.md`: access routes, configuration, and operational permissions; available only on the administrator's machine, outside Git.
- [Supporting knowledge](references/01_supporting-knowledge.md): limits on reusing teaching material and sample code; not required to run the application.
- Private catalog at `docs/references/02_private-source-catalog.md`: routes to original materials on the administrator's machine, outside Git.

## Sources of authority

The PRD owns product requirements and decisions. Source, schemas, configuration, and tests own executable behavior; guides point to those owners instead of copying APIs or command inventories. Architecture explains rationale and boundaries; it does not certify acceptance. Run results, timing measurements, audits, and deployment history belong in `plans/reports/` and do not replace product requirements. [.gitignore](../.gitignore) protects private guides, golden answers, and operational data. [Agent working rules](../AGENTS.md) govern agent coordination, verification, and safety.
