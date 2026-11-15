from .base import BaseAdapter, COMMON_INSTRUCTIONS, register


@register
class GeminiAdapter(BaseAdapter):
    key = "gemini"
    label = "Google Gemini CLI"
    skill_root = ".gemini/skills"
    instruction_files = {"GEMINI.md": COMMON_INSTRUCTIONS}
    extra_files = {
        ".gemini/commands/kataliarc/status.toml": '# KatalIArc managed\ndescription = "Resume KatalIArc architecture decision work."\nprompt = "Read .kataliarc/ artifacts and continue the relevant architecture decision workflow."\n'
    }
    executable = "gemini"
