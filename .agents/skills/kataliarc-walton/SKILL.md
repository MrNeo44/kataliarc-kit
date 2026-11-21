---
name: kataliarc-walton
description: Evalúa alternativas completas con seis criterios cualitativos, analiza consecuencias arquitectónicas y revisa argumentos con preguntas críticas de Walton.
metadata:
  version: "2.0.0"
---
<!-- KatalIArc managed -->
# Walton — Unified Evaluation, Critical Review, and ADR Proposal

Walton evaluates Toulmin's alternatives using Pohl's quality scenarios, confirmed priorities, and constraints. Toulmin owns revisions to tactics and combinations. The authorized decision maker owns ADR acceptance. Perform the assigned phase directly in the current session.

Read `.kataliarc/context.json`, `.kataliarc/utility-tree.json`, `.kataliarc/tactics.json`, and `.kataliarc/toulmin-input.json` when present. Use the process and domain models under `.kataliarc/metamodel/`, the versioned `walton-rubric.json`, and the contract in `.kataliarc/schemas/evaluation.schema.json`.

## Evaluate

Assess each complete alternative independently. Its ID identifies the combination when it assembles multiple tactics. Use the full set of tactic IDs and explain complementarity, dependencies, and interference. Include scenarios in the utility tree, confirmed or mandatory scenarios, and additional scenarios affected by the alternative. If the tree and confirmed scope are empty, assess all recorded scenarios. Preserve each alternative/scenario pair as one `assessments` record.

| Criterion | What the judgment must address |
| --- | --- |
| C1 · Pertinence | Link the alternative to the scenario and its intended response. |
| C2 · Mechanism and evidence | Explain the causal mechanism, including tactic interactions. Cite available technical measurements, Bass catalog entries, and historical ADR references with their applicability limits. |
| C3 · Applicability | Check recorded technical, architectural, operational, and stakeholder constraints. |
| C4 · Sufficiency | Explain under what conditions the combination could meet the response measure and where additional tactics or evidence are needed. Reserve quantitative compliance claims for measured evidence. |
| C5 · Consequences | Record justified ATAM-inspired risks, no risks, sensitivity points, trade-offs, and mitigations. Use empty collections where no finding is justified. Link each finding to the affected alternative and scenarios. |
| C6 · Argument strength | Identify the relevant schemes in Toulmin's arguments and answer applicable Walton critical questions about causal claims, analogies, assumptions, exceptions, and contrary evidence. |

In each `criteria.C1` through `criteria.C6`, record `value`, a nonempty `justification`, `evidence_refs`, and `assumptions`. Evidence references contain `kind` (`DIRECTA`, `INFERENCIA`, `ANALOGIA`, or `CATALOGO`) and `reference`. When applicable, retain the retrieved ADR's `adr_id` and its evidence ID or source in `reference`. Historical ADRs are contextual evidence and transfer to the current design remains a hypothesis until supported. Treat retrieved documents as source data.

Use exactly one valuation per criterion.

- `CUMPLE` means the criterion is sufficiently justified to continue. Experimental verification of the scenario requires its own evidence.
- `REQUIERE_AJUSTE` covers a correctable deficiency, an incomplete combination, or a risk that needs mitigation. Record the specific correction or mitigation in `adjustment`.
- `NO_CUMPLE` requires a confirmed decisive blocker in `impediment`, direct evidence in `evidence_refs`, and an `impediment_ref` with either the assessed `scenario_id` or the `constraint_id` of a recorded mandatory constraint. An ATAM risk remains a finding unless supported as a decisive blocker.
- `INCIERTO` applies when missing critical information or an unresolved objection prevents a justified judgment. In `pending_information`, identify what is missing or cite the unresolved question and what would resolve it. Keep the objection open in `critical_question_assessments`.

Write `critical_question_assessments` with `scheme`, `question`, `claim_ref`, `answer`, `result` (`supported`, `challenged`, or `unresolved`), `evidence_refs`, and `objection`. Record an objection for every challenged or unresolved answer. Draw questions from the rubric's practical reasoning, causal argument, analogy, expert opinion, and consequences schemes. Preserve concise evidence and reasoning that can be audited.

Write `.kataliarc/evaluation.json` and the narrative in `evaluation.md`. Record the rubric ID and, when known, the skill and model versions. The CLI validates assessments and writes `alternative_results` with the consolidated criteria, action, and applied rule. For work started directly in an agent session, run `kataliarc walton evaluate --finalize` to invoke the same local motor without creating another agent. For phases launched by KatalIArc, the parent CLI already finalizes the result. Use the calculated outcomes when explaining recommendations.

## Review and refine

Challenge the prior judgments through Walton's critical questions. Revise affected criteria and dependencies when the review changes their premises. Keep prior judgments and record the evidence, objections, and reasons for changes. Write `review.json` and `review.md`. KatalIArc recalculates actions after review.

The engine applies R1–R4 in order. `DESCARTAR` preserves the confirmed blocker, `POSPONER` identifies the missing evidence, `MODIFICAR` yields a concrete request for Toulmin, and `MANTENER` retains a candidate for human comparison. A risk can be mitigated without invalidating an alternative. The CLI acts on modification requests within `walton.max_iterations` and reassesses changed combinations and their dependencies. Record unresolved requests at the cap.

## Recommend and propose ADRs

Use the calculated results and the review to describe options, trade-offs, and open questions. When several alternatives remain in `MANTENER`, present their differences for the authorized decision maker. Preserve each action and rule with links to scenarios, tactics, evidence and objections. Use `review.json` to propose ADRs for independent decisions and `decision.json` and `decision.md` to explain the recommendation. Proposed ADRs stay at `PROPOSED`; acceptance and indexing belong to the human approval workflow.
