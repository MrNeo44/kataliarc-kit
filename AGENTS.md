<!-- KatalIArc managed -->
# KatalIArc Kit

Use `.kataliarc/` as the architecture decision record. Preserve traceability and uncertainty labels. Record hypotheses and evidence separately, and distinguish qualitative judgments from verified compliance. Keep decisions provisional when evidence or stakeholder confirmation is missing.

When coordinating a KatalIArc methodology phase in the main Codex session, delegate the requested work to the matching subagent and wait for its result.

- `pohl` elicits stakeholder context and quality scenarios, records confirmed priorities, and organizes the utility tree. It follows `kataliarc-pohl`.
- `toulmin` designs architectural alternatives and justifies their tactics and patterns. It follows `kataliarc-toulmin`.
- `walton` evaluates alternatives against scenarios, reviews arguments, and recommends an outcome. It follows `kataliarc-walton`.

The TOML file under `.codex/agents/` defines each subagent's role and scope. The corresponding `SKILL.md` defines the method and artifact contracts. A subagent carrying out an assigned phase applies its skill directly in its own session and reports the result. If the matching subagent cannot be started, apply the relevant skill in the current session. The authorized decision maker approves ADRs.
