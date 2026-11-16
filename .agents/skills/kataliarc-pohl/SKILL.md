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

### How to use Pohl

1. Add the client's available information to `.kataliarc/context.md` and review the existing `.kataliarc/context.json`.
2. Run `kataliarc pohl elicit` to structure the context, requirements, constraints, and quality scenarios in `context.json`. Review the result and resolve or preserve any marked unknowns.
3. Confirm scenario priorities with the client representative, then run `kataliarc pohl prioritize`. It records confirmed priorities in `context.json` and groups scenario IDs in `utility-tree.json`.
4. Run `kataliarc validate` to check that the utility-tree references point to existing scenarios under the correct quality attributes.
5. Continue with `kataliarc toulmin design` once the scenarios and constraints are ready to hand off.

Preserve provenance and missing information; do not turn inferences into facts. Set priority to `A`, `M`, or `B` only when the client representative confirms it. Keep `mandatory` separate from priority. When prioritizing, update priority in `context.json` and keep the utility tree as ID references only.

If a later stage reveals changed or missing requirements, return to the relevant Pohl elicitation step and update the traceable context and scenarios before design continues.
