# Quality Evaluation

The [PRD](02_product-requirements.md) owns cases, thresholds, and acceptance decisions. A golden is an evidence-backed answer reviewed by a person; a sample email or newly generated report is not a golden. Keep answers outside runtime and application images. Never expose them through prompts, tools, or APIs to improve a score.

## Find the evaluation owner

| Task | Executable owner |
| --- | --- |
| Select cases and inputs | [Cases](../evals/cases/), [fixtures](../evals/fixtures/) |
| Prepare, review, lock, and verify goldens | [Golden CLI](../evals/golden.py) |
| Collect an unapproved live run | [Collector](../evals/runner/collect.py) |
| Export and score reviewed outputs | [Runner](../evals/runner/run.py), [scoring](../evals/scoring/) |
| Inspect evidence for review | [Review reader](../evals/review_bundle.py) |
| Protect an approved snapshot | [Regression CLI](../evals/regression.py) |
| Record/replay report generation | [Generation replay](../evals/runner/replay.py) |
| Record/replay web collection | [Web replay](../evals/runner/web_replay.py) |

Use each module's `--help` in the backend environment for current arguments. Goldens belong in `evals/golden/`, outputs/cassettes/reviews in `evals/results/`, and private inputs in `evals/fixtures/private/`, all excluded from Git. Do not overwrite artifacts to make checks pass or repeat the prepared Google seed.

## Review and acceptance

1. Fix the case version, input, and company identity. The original assignment slides are the case authority; a seeded Gmail email does not determine case wording. Preserve corrected URLs. Do not add a subject, meeting date, or setup instructions to source email text.
2. Keep supplemental calendar/PDF inputs separate from source email and record provenance. The assignment supplies no company-profile PDF bytes; a prepared document is not an official company profile. Record missing attachments instead of filling the context with golden answers.
3. Prepare facts and checklists from independent sources, retaining locations and checksums. Review before locking. Unsupported facts need evidence or an explicit missing-data expectation, never an invented answer. Source or answer changes require a new version and review.
4. Collect live output against the fixed input. Identity confirmation in the collector does not approve reports, email sending, or KB storage. Keep goldens out of collection. Score against the exported effective input, without silently substituting a newer email.
5. Review the exact frozen output against the exact golden, binding both checksums. Review facts, significance, readiness criteria, independent sources, and news dates. A review of another version does not transfer to this run.
6. Use the scorer. Without valid human review, report structural checks only, not factual accuracy, completeness, or acceptance. An independent agent review can assist comparison but cannot replace the user's confirmation.

Checksums detect accidental changes; they are not signatures against someone who can edit both content and hashes. Do not assign a reviewer or lock merely because an earlier batch was approved. Old datasets and outputs do not automatically become new versions. Batch history belongs in `plans/reports/` and private artifacts.

## Quality judgments

URL counts establish neither source independence nor factual correctness. Evidence must support the correct entity, time, and claim. Header, update, and retrieval dates do not automatically establish publication dates. Out-of-window news belongs in historical context rather than freshness credit. Record incorrect claims outside the golden too; do not score only what the system remembered.

Assess depth through named products and their purpose, evidenced deployments/partners, correctly scoped figures, relevant recent news, and specific questions for unresolved points. When sources are missing, judge how the report expresses gaps rather than demanding invented facts to fill a quota. Needs analysis must retain its evidence and inference label.

Review customer email separately: a reply when customer email exists, or an opening message when appropriate. Exclude internal research and private information, and reject invented capabilities or commitments. Approval to send is not proof of full PRD compliance.

Performance targets differ from processing timeouts. PRD timing includes queueing and retries until Markdown persistence; exclude identity-confirmation waiting only with valid timestamps. Active processing time cannot replace the end-to-end measure. Do not backfill missing timestamps or claim old outputs passed. [Scoring](../evals/scoring/) owns formulas and fields; never change thresholds after a run to obtain a pass.

## Regression boundaries

An approved report reference protects its input, recipients, choices, and content snapshot. It does not prove the quality of fresh generation. Content changes require review, not automatic reference updates.

Generation replay exercises prompt/schema construction and citation repair against recorded provider responses and frozen inputs. Web replay exercises collection logic against recorded search/scrape responses. Do not substitute an old report for a provider response or fall back to the network on a cassette/input mismatch. Recording calls real providers, incurs costs, and requires authorized data scope.

Neither replay scope proves the full workflow. SQL, database authentication/auditing, Google, checkpoints/approvals, and provider transport/retry need separate checks. Cassettes may contain private data but must never contain credentials. Replay does not measure stochastic stability, live sources, production latency, or factual accuracy. Execution evidence belongs in `plans/reports/`, outside evergreen guidance.
