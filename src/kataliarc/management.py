"""Read-only diagnostics and conservative local resource updates."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from importlib.metadata import version, PackageNotFoundError

from .adapters import ADAPTERS, get_adapter

MANIFEST = "managed-files.json"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _say(items: list[dict], as_json: bool) -> int:
    if as_json:
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        for item in items:
            print(f"{item['status']:<7} {item['message']}")
    return 1 if any(item["status"] == "ERROR" for item in items) else 0


def doctor(project: Path, *, as_json: bool = False) -> int:
    """Check project state without writing to it."""
    project = project.resolve()
    data = project / ".kataliarc"
    checks: list[dict] = []
    def add(status: str, message: str) -> None:
        checks.append({"status": status, "message": message})
    try:
        installed = version("kataliarc-kit")
    except PackageNotFoundError:
        installed = "source checkout"
    add("OK", f"KatalIArc version: {installed}")
    try:
        config = json.loads((data / "config.json").read_text(encoding="utf-8"))
        agent = config.get("agent")
        if agent not in ADAPTERS:
            add("ERROR", "config.json: proveedor ausente o desconocido")
        else:
            adapter = get_adapter(agent)
            if config.get("scope") == "user":
                adapter.configure_global()
            add("OK", f"Proveedor configurado: {adapter.label}")
            add("OK" if adapter.detect() else "WARNING", f"Proveedor disponible: {adapter.executable}" if adapter.detect() else f"No se encuentra {adapter.executable} en PATH")
            missing = adapter.validate(project)
            add("ERROR" if missing else "OK", "Integración incompleta: " + ", ".join(missing) if missing else "Skills e instrucciones presentes")
        if config.get("language") not in {"es", "en"}:
            add("ERROR", "Idioma inválido en config.json")
        else:
            add("OK", f"Idioma: {config['language']}")
        knowledge = config.get("knowledge_sources", [])
        for entry in knowledge:
            path = Path(entry.get("path", "")).expanduser()
            add("OK" if path.is_dir() else "WARNING", f"Fuente de conocimiento {path}: {'disponible' if path.is_dir() else 'ruta inexistente'}")
        if not knowledge:
            add("OK", "Fuentes de conocimiento no configuradas")
    except (OSError, json.JSONDecodeError) as exc:
        add("ERROR", f"Configuración ausente o ilegible: {exc}")
    for filename in ("context.json", "utility-tree.json", "tactics.json", "evaluation.json", "review.json", "decision.json"):
        path = data / filename
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
            add("OK" if isinstance(parsed, dict) else "ERROR", f"JSON {filename}: {'válido' if isinstance(parsed, dict) else 'se esperaba objeto'}")
        except (OSError, json.JSONDecodeError) as exc:
            add("ERROR", f"JSON {filename}: {exc}")
    source_root = data
    for filename in ("context.schema.json", "utility-tree.schema.json", "tactics.schema.json", "evaluation.schema.json", "adr.schema.json"):
        try:
            schema = json.loads((source_root / "schemas" / filename).read_text(encoding="utf-8"))
            add("OK" if isinstance(schema, dict) else "ERROR", f"Schema {filename}: {'presente' if isinstance(schema, dict) else 'inválido'}")
        except (OSError, json.JSONDecodeError) as exc:
            add("ERROR", f"Schema {filename}: {exc}")
    try:
        domain = json.loads((source_root / "metamodel" / "domain.json").read_text(encoding="utf-8"))
        valid_domain = isinstance(domain, dict) and isinstance(domain.get("entities"), dict) and isinstance(domain.get("relationships"), list)
        add("OK" if valid_domain else "ERROR", "Metamodelo de dominio presente" if valid_domain else "Metamodelo de dominio inválido")
    except (OSError, json.JSONDecodeError) as exc:
        add("ERROR", f"Metamodelo de dominio ausente o inválido: {exc}")
    from .adr import validate_record
    decisions_dir = data / "decisions"
    for adr_file in decisions_dir.glob("ADR-*.json") if decisions_dir.is_dir() else []:
        try:
            validate_record(json.loads(adr_file.read_text(encoding="utf-8")))
            add("OK", f"ADR {adr_file.stem}: válido")
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            add("ERROR", f"ADR {adr_file.stem}: inválido ({exc})")
    process_path = source_root / "metamodel" / "process.md"
    add("OK" if process_path.is_file() and process_path.stat().st_size else "ERROR", "Flujo metodológico presente" if process_path.is_file() and process_path.stat().st_size else "Flujo metodológico ausente o vacío")
    for diagram in ("process.mmd", "domain.mmd"):
        diagram_path = source_root / "metamodel" / diagram
        valid_diagram = diagram_path.is_file() and diagram_path.stat().st_size > 0
        add("OK" if valid_diagram else "ERROR", f"Diagrama {diagram} {'presente' if valid_diagram else 'ausente o vacío'}")
    manifest_path = data / MANIFEST
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            add("OK" if manifest.get("files") else "WARNING", "Manifiesto de archivos gestionados válido")
        except (OSError, json.JSONDecodeError):
            add("ERROR", "Manifiesto de archivos gestionados inválido")
    else:
        add("WARNING", "No hay manifiesto de archivos gestionados (instalación anterior)")
    add("OK" if os.access(project, os.W_OK) else "ERROR", f"Permisos de escritura: {project}")
    return _say(checks, as_json)


def update(project: Path, *, dry_run: bool = False, yes: bool = False) -> int:
    """Refresh only files listed in the KatalIArc manifest; preserve edits."""
    project = project.resolve()
    data = project / ".kataliarc"
    try:
        config = json.loads((data / "config.json").read_text(encoding="utf-8"))
        agent = config["agent"]
        if agent not in ADAPTERS:
            raise ValueError(f"Proveedor desconocido: {agent}")
        old = json.loads((data / MANIFEST).read_text(encoding="utf-8"))
    except (OSError, KeyError, json.JSONDecodeError, ValueError) as exc:
        print(f"No se puede actualizar: falta una configuración/manifiesto válidos ({exc}). Ejecuta kataliarc init para adoptar los archivos existentes.", file=sys.stderr)
        return 2
    source = Path(__file__).resolve().parent
    package_root = source / "resources"
    candidates: dict[str, Path] = {}
    for relative in old.get("files", {}):
        if relative.startswith(".kataliarc/schemas/") or relative.startswith(".kataliarc/metamodel/"):
            parts = relative.split("/")
            candidates[relative] = package_root / parts[1] / parts[2]
        else:
            candidates[relative] = None
    # Source-backed resources map by basename for skills and use adapter definitions for instructions.
    adapter = get_adapter(agent)
    if config.get("scope") == "user":
        adapter.configure_global()
    for skill in ("pohl", "toulmin", "walton"):
        rel = f"{adapter.skill_root}/kataliarc-{skill}/SKILL.md"
        candidates[rel] = source / "templates" / "skills" / skill / "SKILL.md"
    for rel, contents in {**adapter.instruction_files, **adapter.extra_files}.items():
        candidates[rel] = None  # generated below
    proposed = []
    for rel, src in candidates.items():
        destination = project / rel
        if rel in adapter.instruction_files or rel in adapter.extra_files:
            content = (adapter.instruction_files | adapter.extra_files)[rel].encode("utf-8")
        elif src is not None and src.is_file():
            content = src.read_bytes()
        else:
            continue
        current_hash = _digest(destination) if destination.is_file() else None
        previous_hash = old["files"].get(rel)
        new_hash = hashlib.sha256(content).hexdigest()
        if current_hash == new_hash:
            continue
        conflict = current_hash is not None and current_hash != previous_hash
        proposed.append((rel, destination, content, conflict, new_hash))
    obsolete_skill = f"{adapter.skill_root}/kataliarc-kazman/SKILL.md"
    obsolete_removals = []
    obsolete_conflicts = []
    if obsolete_skill in old.get("files", {}):
        obsolete_path = project / obsolete_skill
        previous_hash = old["files"].get(obsolete_skill)
        current_hash = _digest(obsolete_path) if obsolete_path.is_file() else None
        if current_hash is None or current_hash == previous_hash:
            obsolete_removals.append((obsolete_skill, obsolete_path))
        else:
            obsolete_conflicts.append(obsolete_skill)
    for rel, _, _, conflict, _ in proposed:
        print(f"{'CONFLICT (preserved)' if conflict else 'UPDATE'} {rel}")
    for rel, _ in obsolete_removals:
        print(f"REMOVE obsolete managed skill {rel}")
    for rel in obsolete_conflicts:
        print(f"CONFLICT (preserved obsolete skill) {rel}")
    if dry_run:
        print(f"Dry run: {len(proposed)} actualización(es), {len(obsolete_removals)} eliminación(es) propuesta(s); sin cambios.")
        return 0
    if not yes and sys.stdin.isatty():
        if input("Apply non-conflicting updates? [y/N] ").strip().lower() not in {"y", "yes"}:
            return 0
    try:
        installed_version = version("kataliarc-kit")
    except PackageNotFoundError:
        installed_version = "0.2.0"
    print(f"KatalIArc resources: {old.get('version', 'unknown')} -> {installed_version}")
    new_manifest = {"version": installed_version, "files": dict(old["files"])}
    for rel, destination in obsolete_removals:
        destination.unlink(missing_ok=True)
        try:
            destination.parent.rmdir()
        except OSError:
            pass
        new_manifest["files"].pop(rel, None)
    for rel, destination, content, conflict, digest in proposed:
        if conflict:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            backup = destination.with_name(destination.name + ".kataliarc-backup")
            if not backup.exists():
                backup.write_bytes(destination.read_bytes())
        destination.write_bytes(content)
        new_manifest["files"][rel] = digest
    (data / MANIFEST).write_text(json.dumps(new_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    config["version"] = installed_version
    (data / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Actualización local completada; {len(proposed)} cambio(s) revisado(s).")
    return 0
