from .base import BaseAdapter, COMMON_INSTRUCTIONS, register


@register
class ClaudeAdapter(BaseAdapter):
    key = "claude"
    label = "Claude Code"
    skill_root = ".claude/skills"
    instruction_files = {"CLAUDE.md": COMMON_INSTRUCTIONS}
    executable = "claude"
