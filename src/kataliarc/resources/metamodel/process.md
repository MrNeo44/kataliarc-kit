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
| Evaluate | Walton | Assess each `ArchitecturalAlternative` against each `QualityScenario`; consider drivers and constraints; record `AlternativeAssessment`, `ArchitecturalRisk`, and `TradeOff`; distinguish contribution from compliance. | Produce evaluation and rationale; hand the evaluation and arguments to Walton's critical review. |
| Critically review and propose | Walton | Use Walton's critical questions to challenge evidence, assumptions, causal mechanisms, constraints, risks, and trade-offs; formulate one proposal per independent decision. | Record objections and let KatalIArc persist each ADR as `PROPOSED`. If an objection changes assumptions or evidence, return the affected work for revision. Walton cannot approve. |
| Decide and recommend | Walton | Integrate the reviewed assessment, unresolved objections, evidence, risks, and trade-offs into `ArchitecturalDecision` and `DecisionRationale`. | Provide the recommendation and its limits in the ADR; do not treat the proposal as accepted. |
| Approve or request changes | User / authorized decision maker | Review a specific ADR version and choose accept, reject, or request changes. | Acceptance is recorded with actor, version, and time. Revisions preserve the prior version. Rejection never triggers indexing. |
| Index accepted ADR | Detached KatalIArc worker | Queue indexing after durable approval, build a retrieval projection, and attach it to the configured vector store with provenance metadata without blocking the approval command. | Record `PENDING`, `INDEXING`, `INDEXED`, or `FAILED` separately from approval. An indexing failure leaves the ADR accepted and can be retried. Superseded records are excluded from current-decision retrieval. |

## Pohl elicitation sequence

1. Read existing project context and identify its sources. Ask who supplied important statements when provenance is unclear.
2. Establish the business problem, goals, system boundary, team capabilities, technology environment, requirements, and constraints. Use the corresponding entities in `domain.json`; do not force unknown fields to invented values.
3. Derive candidate architectural drivers and quality attributes from the stated goals, requirements, and constraints. Keep stakeholder statements distinct from agent interpretations.
4. Elicit quality scenarios using stimulus, environment, response, response measure, acceptance criteria, and known context. Record missing information, assumptions, provenance, and evidence status.
5. Identify whether information critical to safe design is missing. Ask targeted questions where possible. If unanswered, record the gap and its impact; do not silently fill it.
6. Ask the client representative to confirm scenario priorities. Until confirmed, leave priority pending/unknown. Keep mandatory constraints separate from priority.
7. Group scenario IDs by quality attribute in the utility tree. The scenario definition and priority remain canonical in `context.json`; do not duplicate them in the tree.
8. Hand the problem, context, constraints, and confirmed or explicitly pending scenarios to Toulmin. Do not propose tactics or alternatives as part of Pohl's role.

## Feedback and stop conditions

- During design, evaluation, or review, newly discovered requirements or changed assumptions return to Pohl for clarification and scenario updates.
- If critical information prevents a responsible architectural recommendation, record the missing information, assumptions, risks, critical questions, and validation actions, and stop short of recommending an alternative.
- A process stage may be skipped only when its inputs are already available and traceable; record that basis.
