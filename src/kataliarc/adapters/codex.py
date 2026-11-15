from .base import BaseAdapter, COMMON_INSTRUCTIONS, register


@register
class CodexAdapter(BaseAdapter):
    key = "codex"
    label = "OpenAI Codex"
    skill_root = ".agents/skills"
    instruction_files = {"AGENTS.md": COMMON_INSTRUCTIONS}
    executable = "codex"
