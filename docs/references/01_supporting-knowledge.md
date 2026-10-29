# Course Material and Sample Code

Find original material through the private catalog at `docs/references/02_private-source-catalog.md` on the administrator's machine. Course material and samples are neither the chosen design nor evidence of successful execution. The [PRD](../02_product-requirements.md) owns scope; [architecture](../04_architecture-and-safety.md) owns current design decisions.

## When to consult the originals

The Email Assistant assignment is the requirements source. Tool Harness, Orchestration, Security/Governance, Evaluation, and AgentOps lessons explain the design background. Drive, Fulfillment, coding-agent, and customer-service examples do not expand this product's business scope.

Sample tool loops, Gmail/Calendar integrations, RAG, and telemetry are references, not proof of compliance with required roles, version-bound approval, or duplicate-send protection. Direct Gmail sending in samples needs authorization and approval gates; a prompt change does not create a security boundary. Sample tools that create/change/delete calendar events or alter email state are not default project permissions.

Registry examples with schema/auth/scope/rate/audit TODOs or in-memory identity/rate/audit state do not prove production protection. Some examples use simulated CRM data. In-memory cache/BM25 does not establish durable memory across restarts. GraphRAG, vector databases, MCP/A2A, and agent managers remain options rather than requirements.

Anonymous Admin access in a sample monitoring stack is unsuitable for a public demo. Slide ports, models, and prices are not current configuration. Do not unpack entire sample archives into the repository: some contain dotenv files or tokens, whose credentials must not be read or reused. File inventories and static inspection results belong in research reports, not the operating guide.

## Evaluation interpretation traps

- Hit@K measures whether at least one relevant result is retrieved. Recall@K measures the proportion of all relevant results retrieved. They coincide only when each query has one relevant result.
- Evaluation slide S23 incorrectly states `4 / 6 = 0.5`; the result is approximately 0.667. Some Context Relevance/Recall and Precision/Recall labels are mixed; check the denominator before applying a formula.
- Exact Match, BLEU/ROUGE, and word overlap do not establish factual correctness for an open-ended briefing. LLM-as-a-judge cannot replace independent evidence, answers, and confirmed human review.
- General benchmarks and pass@k cannot replace the business cases or the proportion of correctly handled emails.

For library/API decisions, consult current documentation and verify with project source/tests. The course material has not been fully executed and certifies neither dependencies, authentication, nor integration quality. The project's scoring policy belongs in the [evaluation guide](../05_evaluation-guide.md).
