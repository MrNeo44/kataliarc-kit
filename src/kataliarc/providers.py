"""Adaptadores de agente. El núcleo usa un contrato pequeño intercambiable."""
from dataclasses import dataclass
import shutil
import subprocess
from pathlib import Path


@dataclass
class AgentResult:
    returncode: int
    error: str | None = None


class CodexProvider:
    """Invoca Codex CLI con su configuración de permisos predeterminada."""

    def run(self, prompt: str, cwd: Path) -> AgentResult:
        executable = shutil.which("codex")
        if not executable:
            return AgentResult(2, "No se encontró Codex CLI. Instálalo o ejecuta la fase sin --with-agent.")
        try:
            result = subprocess.run([executable, "exec", prompt], cwd=cwd, check=False)
            return AgentResult(result.returncode)
        except OSError as exc:
            return AgentResult(2, f"No se pudo ejecutar Codex: {exc}")


class AgentProvider:
    """Invokes the selected local agent in its documented prompt mode."""
    COMMANDS = {
        "codex": ("codex", "exec"),
        "claude": ("claude", "-p"),
        "gemini": ("gemini", "-p"),
        "copilot": ("copilot", "-p"),
    }

    def run(self, agent: str, prompt: str, cwd: Path) -> AgentResult:
        command = self.COMMANDS[agent]
        executable = shutil.which(command[0])
        if not executable:
            return AgentResult(2, f"No se encontró {command[0]} CLI. Instálalo o ejecuta la fase sin --with-agent.")
        try:
            result = subprocess.run([executable, *command[1:], prompt], cwd=cwd, check=False)
            return AgentResult(result.returncode)
        except OSError as exc:
            return AgentResult(2, f"No se pudo ejecutar {command[0]}: {exc}")
