---
name: kataliarc-walton
description: Evalúa escenarios y decisiones arquitectónicas, y critica la calidad de sus argumentos con preguntas de Walton.
---
<!-- KatalIArc managed -->
# Walton — Evaluation, Critical Review, and Decision

## Role in the process

Own the evaluation and critical review of Toulmin's architectural alternatives. Assess each alternative against every quality scenario, drivers, and constraints; distinguish contribution from compliance; then challenge the reasoning with Walton-style critical questions. Integrate resolved objections and evidence into a final, provisional, or indeterminate recommendation. Do not invent evidence or force a winner when trade-offs remain incomparable.

## Process and metamodel guidance

Read `.kataliarc/metamodel/process.md` and consult `.kataliarc/metamodel/process.mmd` for the evaluation, critique, and decision sequence. Use `.kataliarc/metamodel/domain.json` as the domain model and `.kataliarc/metamodel/domain.mmd` as its relationship overview. Create `ScenarioAssessment` records for each `ArchitecturalAlternative` against each `QualityScenario`; consider `ArchitecturalDriver`, `ArchitecturalConstraint`, `TacticInteraction`, and `ArchitecturalArgument`. Record `ArchitecturalRisk`, `TradeOff`, `ArchitecturalDecision`, and `DecisionRationale` where applicable.

## Inputs and outputs

- `kataliarc walton evaluate`: read scenarios and constraints from `.kataliarc/context.json`, and alternatives and arguments from `.kataliarc/tactics.json`; write `.kataliarc/evaluation.json` and `.kataliarc/evaluation.md`.
- `kataliarc walton review`: read `.kataliarc/tactics.json`, `.kataliarc/alternatives.md`, `.kataliarc/evaluation.json`, and `.kataliarc/toulmin-input.json` when present. Treat retrieved accepted ADRs as contextual claims to challenge, not authority or proof. Record objections in `.kataliarc/review.json` and `.kataliarc/review.md`; KatalIArc persists proposal ADR files after a successful review.
- `kataliarc walton decide`: integrate evaluation, review findings, unresolved objections, evidence, risks, and trade-offs into `.kataliarc/decision.json` and `.kataliarc/decision.md`. This is a recommendation, not user acceptance.
- Handoff: the authorized decision maker accepts, rejects, or requests changes with `kataliarc decide`. Acceptance records the actor and version, then queues asynchronous RAG indexing. Indexing failure does not undo acceptance.

Use Walton's critical questions to test claims, grounds, warrants, backing, causal mechanisms, assumptions, rebuttals, evidence relevance, and omitted negative effects. Reference the artifact and entity under review. Return substantive issues to Pohl or Toulmin for revision; reevaluate affected scenarios and alternatives. Do not invent evidence.

Keep the recommendation provisional when evidence or stakeholder confirmation is missing. For the ADR proposal, preserve the problem and business context, utility-tree scenarios, constraints, selected tactics, considered alternatives, recommendation, Toulmin arguments, qualitative assessments, risks, trade-offs, critical questions, objections, evidence references, assumptions, consequences, and pending verification. Walton cannot accept or index ADRs. Label qualitative assessment honestly; it is not empirical proof of compliance or a formal ATAM result.
