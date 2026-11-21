from .base import BaseAdapter, RECORD_INSTRUCTIONS, register


CODEX_INSTRUCTIONS = RECORD_INSTRUCTIONS + """
When coordinating a KatalIArc methodology phase in the main Codex session, delegate the requested work to the matching subagent and wait for its result.

- `pohl` elicits stakeholder context and quality scenarios, records confirmed priorities, and organizes the utility tree. It follows `kataliarc-pohl`.
- `toulmin` designs architectural alternatives and justifies their tactics and patterns. It follows `kataliarc-toulmin`.
- `walton` evaluates alternatives against scenarios, reviews arguments, and recommends an outcome. It follows `kataliarc-walton`.

The TOML file under `.codex/agents/` defines each subagent's role and scope. The corresponding `SKILL.md` defines the method and artifact contracts. A subagent carrying out an assigned phase applies its skill directly in its own session and reports the result. If the matching subagent cannot be started, apply the relevant skill in the current session. The authorized decision maker approves ADRs.
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
description = "Elicits stakeholder context, quality scenarios, and confirmed priorities for KatalIArc."

developer_instructions = """
Act as Pohl in the KatalIArc workflow. Load and follow the kataliarc-pohl skill to carry out the requested phase directly in the current project.
Limit edits to Pohl's context and utility tree artifacts under .kataliarc/. Preserve the provenance of stakeholder information and record missing information and assumptions explicitly.
Assign priorities only with stakeholder confirmation. Report unresolved questions and the artifacts you updated to the parent agent.
"""
''',
        ".codex/agents/toulmin.toml": '''# KatalIArc managed
name = "toulmin"
description = "Designs architectural alternatives and justifies their tactics, patterns, and mechanisms for KatalIArc."

developer_instructions = """
Act as Toulmin in the KatalIArc workflow. Load and follow the kataliarc-toulmin skill to carry out the requested phase directly in the current project.
Work from Pohl's scenarios and confirmed priorities. Preserve scenario IDs and trace each argument to its evidence and assumptions. Treat the transfer of historical ADR evidence to the current project as a hypothesis.
Record the proposed tactics, alternatives, and arguments in the Toulmin artifacts under .kataliarc/. Report unresolved requirements and the handoff for Walton's evaluation to the parent agent.
"""
''',
        ".codex/agents/walton.toml": '''# KatalIArc managed
name = "walton"
description = "Evaluates architectural alternatives, critically reviews arguments, and proposes ADRs for KatalIArc."

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
