# ADR-001: Read-only ADR retrieval for Toulmin design

- Status: proposed; pending validation against the project's actual vector store.
- Date: 2026-11-14

## Context

Toulmin design needs historical architecture decisions as contextual backing. The historical ADR corpus must remain read-only, and retrieval must not be available to the other methodological roles. The design phase also needs bounded repository evidence without executing or changing the target repository.

## Decision

The `design --with-agent` orchestration prepares a bounded local repository analysis, then searches an explicitly configured existing OpenAI vector store through its vector-store search endpoint. It creates scenario-to-ADR queries and scenario/tactic-to-ADR queries, preserving result IDs, query routes, source metadata, and similarity scores. Retrieved statements remain historical evidence; their transfer to the current design is labeled as an inference/hypothesis. The provider receives the prepared `.kataliarc/toulmin-input.json` and must produce Toulmin arguments with claim, grounds, warrant, backing, qualifier, and rebuttal.

Only the design orchestration invokes retrieval. Other phases continue without RAG. The integration never creates, uploads, or modifies vector-store contents. Repository inspection is bounded, skips secret-like paths, and does not execute code. Search is opt-in through a configured vector-store ID and can be disabled with `--no-rag`.

## Alternatives considered

- Let every methodological role query the ADR store: rejected because the user explicitly scoped historical retrieval to Toulmin.
- Let the agent call the retrieval API directly: rejected because API access, query bounds, and source traceability would be less controlled.
- Copy ADRs into the target repository: rejected because it duplicates the corpus and can expose unrelated historical material.

## Trade-offs and risks

- Search adds network dependence and may return irrelevant or incomplete chunks; the workflow therefore continues with warnings and keeps source metadata for review.
- Similarity scores are retrieval signals, not evidence of correctness or applicability.
- Sequential bounded queries are transparent but may be slower than a future batched retrieval design.
- The existing store ID, corpus quality, and real account permissions have not been validated in this implementation run; no live API call was made.

## Pending validation

- Configure the intended vector-store ID and confirm it contains the historical ADR corpus.
- Review retrieved chunks and their source references with representative ADRs.
- Confirm API project permissions and operational cost with a deliberate manual design run.
