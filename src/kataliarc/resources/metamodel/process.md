# KatalIArc architecture decision process

This document describes the process flow shared by the methodological skills. See [`process.mmd`](process.mmd) for its activity diagram. The domain vocabulary is in `domain.json`; see [`domain.mmd`](domain.mmd) for its entity diagram. The installed copies are `.kataliarc/metamodel/`. Follow the process as a sequence with feedback loops, not as a requirement to produce every entity in every project.

## Process rules

- The stakeholder provides context, needs, and constraints; the agent records their provenance.
- The agent identifies drivers, missing information, assumptions, and risks before proposing designs.
- If critical information is missing, ask the stakeholder or record the gap, assumptions, risks, and validation actions. Do not present a recommendation as settled when its basis is insufficient.
- Priorities are confirmed by the client representative. A priority is distinct from whether a constraint is mandatory.
- Alternatives are compared against quality scenarios, constraints, and trade-offs. Review can send the work back for revision or validation.
- The outcome includes its rationale, drivers, alternatives, trade-offs, missing information, assumptions, risks, evidence, and limits. Preserve provisional status when confirmation or evidence is missing.

## Stages and skill ownership

| Stage | Owner | Work and domain concepts | Output / next step |
|---|---|---|---|
| Elicit and frame | Pohl | Gather `Stakeholder`, `BusinessProblem`, `BusinessGoal`, `BusinessRequirement`, `ArchitecturalContext`, and `ArchitecturalConstraint`; identify `ArchitecturalProblem`, `ArchitecturalDriver`, `QualityAttribute`, and measurable `QualityScenario`; mark unknowns and assumptions. | Update `.kataliarc/context.json` and `.kataliarc/context.md`; create/update `.kataliarc/utility-tree.json` as scenario-ID groupings. Ask for critical missing context; otherwise hand scenarios and constraints to Toulmin. |
| Confirm priorities | Pohl with client representative | Organize scenarios by quality attribute using `UtilityTreeBranch`; obtain confirmation for importance/difficulty priorities. | Store scenario details and priority in `context.json`; store only IDs and attribute names in `utility-tree.json`; then hand confirmed scenarios to Toulmin. |
| Design and argue | Toulmin | Consult applicable `ArchitecturalKnowledge`; propose `ArchitecturalTactic` and `ArchitecturalPattern`; explain `PatternTacticInteraction` and `TacticInteraction`; assemble `ArchitecturalAlternative`; construct `ArchitecturalArgument`. | Produce tactics, alternatives, and arguments; hand them to Walton. Historical knowledge informs but does not establish current applicability. |
| Evaluate | Walton | Judge each complete alternative with C1–C6 against each in-scope scenario. Record evidence, assumptions, critical questions, and supported ATAM-inspired findings. | Write `.kataliarc/evaluation.json` and `.kataliarc/evaluation.md`. The CLI validates coverage and applies R1–R4 per alternative. Only `MODIFICAR` triggers a bounded Toulmin refinement. |
| Critically review | Walton | Apply the rubric's Walton schemes. Record evidence, objections, and their status. Revise affected judgments and dependencies with evidence and retain past judgments. | Refresh the evaluation and `.kataliarc/review.json` / `review.md`. The CLI recalculates R1–R4. Keep unresolved claims and human approval explicit. |
| Refine | Toulmin, requested by Walton | Revise only requested tactics, combinations, arguments, or evidence. Toulmin retains ownership of tactic selection and argument construction. | Bounded by `config.json` → `walton.max_iterations` (default 3, maximum 5); each cycle preserves prior assessment summaries and artifact-level observations. Exhausted requests remain unresolved. No automatic alternative acceptance. |
| Propose ADR | Walton | Integrate scenario assessments, critical questions, risks, sensitivities, trade-offs, and unresolved iteration requests into one proposal per independent decision. | KatalIArc persists versioned JSON and Markdown ADRs in `PROPOSED`; approval remains with the authorized decision maker. |
| Decide and recommend | Walton | Integrate the computed actions, reviewed evidence, concerns, trade-offs, and unresolved requests. | Present the differences among candidates kept for human decision. Retain the applied rule and evidence in the proposed ADR. |
| Approve or request changes | User / authorized decision maker | Review a specific ADR version and choose accept, reject, or request changes. | Acceptance is recorded with actor, version, and time. Revisions preserve the prior version. Rejection never triggers indexing. |
| Index accepted ADR | Detached KatalIArc worker | Queue indexing after durable approval, build a retrieval projection, and attach it to the configured vector store with provenance metadata without blocking the approval command. | Record `PENDING`, `INDEXING`, `INDEXED`, or `FAILED` separately from approval. An indexing failure leaves the ADR accepted and can be retried. Superseded records are excluded from current-decision retrieval. |

## Pohl elicitation sequence

1. Read existing project context and identify its sources. Ask who supplied important statements when provenance is unclear.
2. Establish the business problem, goals, system boundary, team capabilities, technology environment, requirements, and constraints. Use the corresponding entities in `domain.json`; do not force unknown fields to invented values.
3. Derive candidate architectural drivers and quality attributes from the stated goals, requirements, and constraints. Use [the ISO/IEC 25010 product quality model](iso-25010-2023.json) as a reference for standard names, and preserve project-specific attributes. Keep stakeholder statements distinct from agent interpretations.
4. Elicit quality scenarios using stimulus, environment, response, response measure, acceptance criteria, and known context. Record missing information, assumptions, provenance, and evidence status.
5. Identify whether information critical to safe design is missing. Ask targeted questions where possible. If unanswered, record the gap and its impact; do not silently fill it.
6. Ask the client representative to confirm scenario priorities. Until confirmed, leave priority pending/unknown. Keep mandatory constraints separate from priority.
7. Group scenario IDs by quality attribute in the utility tree. The scenario definition and priority remain canonical in `context.json`; do not duplicate them in the tree.
8. Hand the problem, context, constraints, and confirmed or explicitly pending scenarios to Toulmin. Do not propose tactics or alternatives as part of Pohl's role.

## Walton evaluation and follow-up

Evaluate each complete alternative against the relevant scenarios. Retain the full tactic combination and assess its interactions. Record one judgment per criterion with its justification, evidence references, and assumptions. The CLI consolidates the judgments per alternative and records the first matching rule.

| Rule | Judgment | Action and follow-up |
|---|---|---|
| R1 | `NO_CUMPLE` requires a decisive blocker supported by direct evidence. Identify it in `impediment` and link it through `impediment_ref` to the assessed scenario or a mandatory constraint. | `DESCARTAR`. Preserve the confirmed blocker and its evidence. |
| R2 | `INCIERTO` applies when missing critical information or an unresolved objection prevents a justified judgment. | `POSPONER`. Record the open question and what would resolve it. |
| R3 | `REQUIERE_AJUSTE` covers a correctable deficiency, an incomplete combination, or a risk with a concrete mitigation. | `MODIFICAR`. Request a bounded refinement from Toulmin. |
| R4 | All six criteria are `CUMPLE`. Each is sufficiently justified to continue. | `MANTENER`. Keep the alternative available for human comparison. |

ATAM-inspired risks remain findings in the assessment. Experimental verification requires its own evidence. `kataliarc walton evaluate --finalize` validates recorded judgments and calculates the outcome locally. Critical review may revise the judgments with evidence. The ADR preserves the calculated rule, evidence, and open objections for the authorized decision maker.

## Feedback and stop conditions

- During design, evaluation, or review, newly discovered requirements or changed assumptions return to Pohl for clarification and scenario updates.
- If critical information prevents a responsible architectural recommendation, record the missing information, assumptions, risks, critical questions, and validation actions, and stop short of recommending an alternative.
- A process stage may be skipped only when its inputs are already available and traceable; record that basis.
