"""Read-only, bounded repository inspection for architecture evidence."""
from __future__ import annotations

import os
from pathlib import Path
import re


SKIP_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "vendor",
    "target", "dist", "build", "out", "coverage", "__pycache__", ".next",
    ".nuxt", ".terraform", ".pytest_cache", ".mypy_cache", ".tox", "Pods",
}
SECRET_DIRS = {".aws", ".ssh", "secrets", "credentials", "private", "certificates"}
SECRET_NAME = re.compile(r"(^\.env($|\.)|secret|credential|token|private.?key|id_rsa|id_ed25519)", re.I)
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".keystore"}
TEXT_SUFFIXES = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java",
    ".kt", ".kts", ".go", ".rs", ".cs", ".cpp", ".c", ".h", ".hpp", ".rb",
    ".php", ".scala", ".swift", ".sql", ".sh", ".bash", ".yml", ".yaml",
    ".toml", ".ini", ".xml", ".properties", ".md", ".rst", ".txt", ".json",
    ".tf", ".dockerfile",
}
SPECIAL_FILES = {
    "Dockerfile", "Makefile", "Procfile", "Justfile", "requirements.txt",
    "Pipfile", "Gemfile", "go.mod", "Cargo.toml", "pom.xml", "build.gradle",
    "settings.gradle", "package.json", "pyproject.toml", "compose.yaml",
    "docker-compose.yml", "README", "README.md", "CONTRIBUTING.md",
}
ARCH_DOC_NAME = re.compile(r"(^readme|architecture|system|design|deployment|adr[-_]|decision)", re.I)
ARCH_SIGNALS = re.compile(
    r"\b(class|interface|struct|module|package|def|function|router|route|endpoint|"
    r"database|repository|cache|queue|broker|retry|timeout|replica|transaction|"
    r"auth|middleware|pool|async|event|service|controller|handler|migration|"
    r"connect|publish|subscribe|consumer|producer|circuit.?breaker)\b",
    re.I,
)
SYMBOL = re.compile(
    r"^\s*(?:export\s+)?(?:abstract\s+)?(?:class|interface|struct|enum|type|module|"
    r"def|function|func|fn)\s+([A-Za-z_$][\w$]*)"
)
LANGUAGES = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".mjs": "JavaScript",
    ".cjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".kt": "Kotlin", ".kts": "Kotlin", ".go": "Go", ".rs": "Rust", ".cs": "C#",
    ".cpp": "C++", ".c": "C", ".h": "C/C++", ".hpp": "C++", ".rb": "Ruby",
    ".php": "PHP", ".scala": "Scala", ".swift": "Swift", ".sql": "SQL",
}


def _is_secret_path(relative: Path) -> bool:
    if any(part.lower() in SECRET_DIRS for part in relative.parts[:-1]):
        return True
    name = relative.name
    return bool(SECRET_NAME.search(name) or relative.suffix.lower() in SECRET_SUFFIXES)


def _kind(path: Path) -> str:
    if path.name.lower().startswith(("readme", "architecture", "system", "design", "adr-", "adr_")):
        return "architecture_document"
    if path.name in SPECIAL_FILES or path.name.lower() in {"requirements-dev.txt", "package-lock.json", "pnpm-lock.yaml"}:
        return "technology_manifest"
    return "source_code"


def _finding(path: Path, relative: Path, text: str, kind: str, line_start: int, line_end: int, excerpt: str, symbol: str | None = None) -> dict:
    result = {
        "id": f"REPO-{len(path.parts)}-{line_start}-{line_end}-{relative.as_posix()}",
        "kind": kind,
        "source": {"path": relative.as_posix(), "line_start": line_start, "line_end": line_end},
        "excerpt": excerpt[:2400],
        "evidence_status": "documentada",
    }
    if symbol:
        result["source"]["symbol"] = symbol
    return result


def analyze_repository(repository: str | Path, *, max_files: int = 320, max_findings: int = 100, max_file_bytes: int = 192_000) -> dict:
    """Collect bounded text evidence without executing or modifying the target."""
    root = Path(repository).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Repository path is not a directory: {root}")

    languages: dict[str, int] = {}
    manifests: list[str] = []
    top_level: set[str] = set()
    findings: list[dict] = []
    warnings: list[str] = []
    files_seen = 0
    files_inspected = 0
    files_skipped_secrets = 0
    truncated = False

    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        relative_dir = current_path.relative_to(root)
        directories[:] = sorted(
            name for name in directories
            if name not in SKIP_DIRS and name.lower() not in SECRET_DIRS
            and not (current_path / name).is_symlink()
        )
        for filename in sorted(filenames):
            file_path = current_path / filename
            relative = file_path.relative_to(root)
            if _is_secret_path(relative):
                files_skipped_secrets += 1
                continue
            if file_path.is_symlink():
                continue
            if file_path.suffix.lower() not in TEXT_SUFFIXES and filename not in SPECIAL_FILES:
                continue
            files_seen += 1
            top_level.add(relative.parts[0] if len(relative.parts) > 1 else ".")
            language = LANGUAGES.get(file_path.suffix.lower())
            if language:
                languages[language] = languages.get(language, 0) + 1
            if filename in SPECIAL_FILES:
                manifests.append(relative.as_posix())
            if files_inspected >= max_files:
                truncated = True
                break
            try:
                if file_path.stat().st_size > max_file_bytes:
                    continue
                raw = file_path.read_bytes()
                if b"\x00" in raw:
                    continue
                text = raw.decode("utf-8", errors="replace")
            except (OSError, UnicodeError):
                continue
            files_inspected += 1
            if len(findings) >= max_findings:
                truncated = True
                break

            lines = text.splitlines()
            kind = _kind(file_path)
            if kind in {"architecture_document", "technology_manifest"}:
                excerpt_lines = lines[:50]
                if excerpt_lines:
                    excerpt = "\n".join(excerpt_lines)
                    findings.append(_finding(file_path, relative, text, kind, 1, len(excerpt_lines), excerpt))
                continue

            matches = []
            for index, line in enumerate(lines):
                if ARCH_SIGNALS.search(line):
                    symbol_match = SYMBOL.match(line)
                    start = max(0, index - 1)
                    end = min(len(lines), index + 3)
                    excerpt = "\n".join(lines[start:end])
                    matches.append((index + 1, min(len(lines), index + 3), excerpt, symbol_match.group(1) if symbol_match else None))
                    if len(matches) >= 3:
                        break
            for line_start, line_end, excerpt, symbol in matches:
                if len(findings) >= max_findings:
                    truncated = True
                    break
                findings.append(_finding(file_path, relative, text, kind, line_start, line_end, excerpt, symbol))
        if truncated:
            break

    if truncated:
        warnings.append(f"Inspection limit reached (max_files={max_files}, max_findings={max_findings}); results are partial.")
    if files_skipped_secrets:
        warnings.append(f"Skipped {files_skipped_secrets} secret-like file(s) by name or location.")

    return {
        "schema_version": "1.0",
        "repository_path": str(root),
        "read_only": True,
        "code_execution": False,
        "summary": {
            "top_level_entries": sorted(top_level),
            "languages_by_file_count": dict(sorted(languages.items())),
            "technology_manifests": sorted(set(manifests)),
            "eligible_files_seen": files_seen,
            "files_inspected": files_inspected,
            "findings_count": len(findings),
            "partial": truncated,
        },
        "findings": findings,
        "warnings": warnings,
    }
