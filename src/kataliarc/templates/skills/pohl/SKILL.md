---
name: kataliarc-pohl
description: Elicita contexto y estructura escenarios de calidad y prioridades confirmadas por el cliente.
---
<!-- KatalIArc managed -->
# Pohl — Elicitation and Utility Tree

## Role in the process

Own the opening process segment: collect stakeholder context, characterize the problem, identify goals, requirements, constraints, quality attributes, and scenarios, then surface missing information and assumptions. Check whether information is sufficient to hand off. Do not design or evaluate architectural alternatives.

## Process and metamodel guidance

Before eliciting, read `.kataliarc/metamodel/process.md` and consult `.kataliarc/metamodel/process.mmd` for the activity flow. Use `.kataliarc/metamodel/domain.json` as the domain model and `.kataliarc/metamodel/domain.mmd` as its relationship overview. Pohl owns the opening stages and priority confirmation: elicit `Stakeholder`, `BusinessProblem`, `BusinessGoal`, `BusinessRequirement`, `ArchitecturalContext`, and `ArchitecturalConstraint`; frame `ArchitecturalProblem` and `ArchitecturalDriver`; identify `QualityAttribute` and elicit measurable `QualityScenario` records. Group scenarios with `UtilityTreeBranch` references. Do not create tactics, alternatives, assessments, or decisions.

## Inputs and outputs

- `.kataliarc/context.md`: free-form context and notes supplied by you or the client. Read this before eliciting; add or clarify stakeholder-provided information here when useful.
- `.kataliarc/context.json`: structured source of truth for business goals, requirements, constraints, quality attributes, scenarios, and confirmed priorities. `kataliarc pohl elicit` updates this file from the supplied context. Do not invent missing facts.
- `.kataliarc/utility-tree.json`: groups scenario IDs under quality attributes. `kataliarc pohl prioritize` updates confirmed priorities in `context.json` and organizes the ID references here. Do not copy scenario descriptions or priorities into the tree.
- Handoff: `kataliarc toulmin design` uses these scenarios to propose tactics and alternatives.

### How to carry out Pohl's phases

Apply the requested phase directly in the current session.

1. Review the stakeholder information in `.kataliarc/context.md`, the existing `.kataliarc/context.json`, and the relevant sources supplied for the project.
2. During elicitation, structure context, requirements, constraints, and quality scenarios in `context.json`. Resolve requirement gaps that the supplied sources can answer and cite the source of each resolution.
3. Ask the stakeholder a targeted question only when the sources leave a requirement gap unresolved. Record the sources checked, the open question, and its impact. When delegated, pass the question to the coordinating session.
4. During prioritization, record stakeholder-confirmed priorities in `context.json` and group scenario IDs in `utility-tree.json`.
5. Use `kataliarc validate` to check that the utility-tree references point to existing scenarios under the correct quality attributes.
6. Report what is ready for Toulmin and any open questions.

Preserve provenance and missing information; do not turn inferences into facts. Set priority to `A`, `M`, or `B` only when the client representative confirms it. Keep `mandatory` separate from priority. When prioritizing, update priority in `context.json` and keep the utility tree as ID references only.

If a later stage reveals changed or missing requirements, return to the relevant Pohl elicitation step and update the traceable context and scenarios before design continues.
