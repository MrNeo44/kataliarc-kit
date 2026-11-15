from .base import BaseAdapter, COMMON_INSTRUCTIONS, register


@register
class CopilotAdapter(BaseAdapter):
    key = "copilot"
    label = "GitHub Copilot"
    skill_root = ".github/skills"
    instruction_files = {".github/copilot-instructions.md": COMMON_INSTRUCTIONS}
    extra_files = {
        ".github/agents/kataliarc-review.agent.md": "---\nname: kataliarc-review\ndescription: Evaluates architecture decisions and critiques argument quality using Walton critical questions.\n---\n\n" + COMMON_INSTRUCTIONS + "\nUse the kataliarc-walton skill to evaluate scenarios, challenge arguments, and record objections and trade-offs.\n"
    }
    executable = "copilot"
