<!-- KatalIArc managed -->
# KatalIArc Kit

Use `.kataliarc/` as the architecture decision record. Preserve traceability and uncertainty labels. Record hypotheses and evidence separately, and distinguish qualitative judgments from verified compliance. Keep decisions provisional when evidence or stakeholder confirmation is missing.

## Codex delegation

Before handing off work, read `.kataliarc/metamodel/process.md` and `process.mmd` to determine the next phase, its owner, and its conditions. Use `.kataliarc/metamodel/domain.json` and `domain.mmd` to identify the artifacts and relationships that the next phase needs. If a phase can be skipped under the process, record which existing traceable inputs justify the skip.

In the main Codex session, delegate the requested work to the matching subagent and wait for its result. Give it the project path, phase, relevant artifact paths or IDs, confirmed constraints, assumptions, and open questions. Review its outputs against the process before choosing the next handoff.

Relay a requirement question to the user only after Pohl checks the supplied project sources and reports what remains unresolved. Return the answers to Pohl so it can update the context and scenarios with their provenance. When a critical question is awaiting a reply in an interactive session, pause the affected handoff. If an answer is unavailable, follow the process stop conditions and carry forward the recorded gap and its impact.

| Subagent | When to delegate and what to send | How to integrate the result |
| --- | --- | --- |
| `pohl` | Delegate elicitation or prioritization. Send stakeholder notes, the existing `context.md` and `context.json`, and any explicit stakeholder confirmation of priorities. | Use the updated context and utility-tree scenario IDs as Toulmin's input. Carry forward gaps and priorities that still need confirmation. |
| `toulmin` | Delegate initial design or a bounded refinement. Send Pohl's scenarios and confirmed priorities, the utility tree, constraints, and `toulmin-input.json` when available. Include the specific review request and affected IDs for a refinement. | Pass the proposed alternatives and traceable arguments to Walton. Route missing requirements or changed scenarios back to Pohl. |
| `walton` | Delegate evaluation, critical review, or recommendation. Send Pohl's scenarios and constraints, Toulmin's alternatives and arguments, the Walton rubric, and any existing evaluation, review, or evidence relevant to the phase. | Use the validated evaluation and actions calculated by KatalIArc. Route bounded design revisions to Toulmin, send newly discovered requirements or changed assumptions back to Pohl, and surface unresolved findings to the decision maker. The authorized decision maker approves ADRs. |

The TOML files under `.codex/agents/` define the subagents. Each assigned subagent applies its corresponding `kataliarc-*` skill directly and reports the changed artifacts, evidence references, and remaining questions. If the matching subagent cannot be started, apply its skill in the current session.
