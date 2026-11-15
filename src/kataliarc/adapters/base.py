"""Shared adapter contract and safe file installation."""
from pathlib import Path
import shutil


class BaseAdapter:
    key = ""
    label = ""
    skill_root = ""
    instruction_files: dict[str, str] = {}
    extra_files: dict[str, str] = {}
    executable = ""
    capabilities: tuple[str, ...] = ("skills", "project instructions")

    def configure_global(self) -> None:
        """Switch resource paths to documented per-user locations where supported."""
        if self.key == "codex":
            self.instruction_files = {".codex/AGENTS.md": COMMON_INSTRUCTIONS}
        elif self.key == "claude":
            self.instruction_files = {".claude/CLAUDE.md": COMMON_INSTRUCTIONS}
        elif self.key == "gemini":
            self.instruction_files = {".gemini/GEMINI.md": COMMON_INSTRUCTIONS}
        elif self.key == "copilot":
            self.skill_root = ".copilot/skills"
            self.instruction_files = {}
            self.extra_files = {}
            self.capabilities = ("user-level skills", "no global instruction file generated")

    def detect(self) -> str | None:
        return shutil.which(self.executable) if self.executable else None

    def validate(self, project: Path) -> list[str]:
        missing = []
        for relative in [self.instruction_files, self.extra_files]:
            for path in relative:
                if not (project / path).is_file():
                    missing.append(path)
        for skill in ("pohl", "toulmin", "walton"):
            if not (project / self.skill_root / f"kataliarc-{skill}" / "SKILL.md").is_file():
                missing.append(f"{self.skill_root}/kataliarc-{skill}/SKILL.md")
        return missing

    def install(self, project: Path, source: Path, *, overwrite: bool = False) -> list[Path]:
        written: list[Path] = []
        skills = source / "templates" / "skills"
        for skill in ("pohl", "toulmin", "walton"):
            src = skills / skill
            dst = project / self.skill_root / f"kataliarc-{skill}"
            if src.is_dir():
                dst.mkdir(parents=True, exist_ok=True)
                for item in src.iterdir():
                    if item.is_file() and self._copy(item, dst / item.name, overwrite):
                        written.append(dst / item.name)
        for relative, contents in {**self.instruction_files, **self.extra_files}.items():
            target = project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if self._write(target, contents, overwrite):
                written.append(target)
        return written

    @staticmethod
    def _write(path: Path, contents: str, overwrite: bool) -> bool:
        if path.exists():
            if not overwrite:
                return False
            try:
                existing = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                return False
            if "KatalIArc managed" not in existing:
                return False
        path.write_text(contents, encoding="utf-8")
        return True

    @staticmethod
    def _copy(source: Path, target: Path, overwrite: bool) -> bool:
        if target.exists():
            if not overwrite:
                return False
            try:
                if "KatalIArc managed" not in target.read_text(encoding="utf-8"):
                    return False
            except (OSError, UnicodeError):
                return False
        shutil.copyfile(source, target)
        return True


COMMON_INSTRUCTIONS = """<!-- KatalIArc managed -->
# KatalIArc Kit

Use `.kataliarc/` as the architecture decision record. Preserve traceability and uncertainty labels; do not treat hypotheses as evidence or contribution as compliance. Follow the installed KatalIArc skills: Pohl for elicitation and utility tree, Toulmin for tactics and argumentation, and Walton for scenario evaluation, critical review, and recommendations. Keep decisions provisional when evidence or stakeholder confirmation is missing.
"""
ADAPTERS: dict[str, type[BaseAdapter]] = {}


def register(cls: type[BaseAdapter]) -> type[BaseAdapter]:
    ADAPTERS[cls.key] = cls
    return cls


def get_adapter(key: str) -> BaseAdapter:
    return ADAPTERS[key]()


from .codex import CodexAdapter
from .claude import ClaudeAdapter
from .gemini import GeminiAdapter
from .copilot import CopilotAdapter
