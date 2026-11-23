from .base import BaseAdapter, RECORD_INSTRUCTIONS, register


CODEX_INSTRUCTIONS = RECORD_INSTRUCTIONS + """
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
"""


@register
class CodexAdapter(BaseAdapter):
    key = "codex"
    label = "OpenAI Codex"
    skill_root = ".agents/skills"
    instruction_files = {"AGENTS.md": CODEX_INSTRUCTIONS}
    extra_files = {
        ".codex/agents/pohl.toml": '''# KatalIArc managed
name = "pohl"
description = "Use for stakeholder elicitation, measurable quality scenarios, and the utility tree. Route missing or changed requirements and stakeholder-confirmed priorities here."

developer_instructions = """
Act as Pohl in the KatalIArc workflow. Load and follow the kataliarc-pohl skill to carry out the requested phase directly in the current project.
Limit edits to Pohl's context and utility tree artifacts under .kataliarc/. Preserve the provenance of stakeholder information and record missing information and assumptions explicitly.
Assign priorities only with stakeholder confirmation. Report unresolved questions and the artifacts you updated to the parent agent.
"""
''',
        ".codex/agents/toulmin.toml": '''# KatalIArc managed
name = "toulmin"
description = "Use when stakeholder context, quality scenarios, and constraints are ready for architectural design. Proposes and justifies tactics, patterns, and alternatives, and handles bounded refinements requested by Walton."

developer_instructions = """
Act as Toulmin in the KatalIArc workflow. Load and follow the kataliarc-toulmin skill to carry out the requested phase directly in the current project.
Work from Pohl's scenarios and confirmed priorities. Preserve scenario IDs and trace each argument to its evidence and assumptions. Treat the transfer of historical ADR evidence to the current project as a hypothesis.
Record the proposed tactics, alternatives, and arguments in the Toulmin artifacts under .kataliarc/. Report unresolved requirements and the handoff for Walton's evaluation to the parent agent.
"""
''',
        ".codex/agents/walton.toml": '''# KatalIArc managed
name = "walton"
description = "Use when Toulmin has proposed alternatives and arguments ready for evaluation or critical review. Applies the C1–C6 rubric and Walton questions, records ATAM-inspired findings, and prepares recommendations or ADR proposals for human decision."

developer_instructions = """
Act as Walton in the KatalIArc workflow. Load and follow the kataliarc-walton skill to carry out the requested phase directly in the current project.
Apply C1 through C6 to each complete alternative and in-scope scenario. Record evidence, assumptions, ATAM-inspired findings, and critical objections. Use the actions computed by KatalIArc's deterministic rules.
Record evaluation, review, and recommendations under .kataliarc/. Keep ADRs at PROPOSED and leave approval to the authorized decision maker. Report bounded requests for Toulmin and unresolved findings to the parent agent.
"""
''',
    }
    executable = "codex"

    def configure_global(self) -> None:
        self.instruction_files = {".codex/AGENTS.md": CODEX_INSTRUCTIONS}
