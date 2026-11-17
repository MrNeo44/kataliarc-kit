"""CLI KatalIArc Kit. Las fases guardan contratos locales revisables."""
import argparse
import getpass
import json
from pathlib import Path
import sys
import subprocess
from typing import Any
import uuid
from datetime import datetime, timezone

from .adapters import ADAPTERS, get_adapter
from .providers import AgentProvider
from .wizard import AGENTS, clear_terminal, play_retro_music, render_banner, select_agent, select_language, select_choice
from .management import MANIFEST, doctor as run_doctor, update as run_update
from .toulmin import build_design_prompt, build_toulmin_input, write_managed_json
from .rag import OpenAIVectorStoreRetriever, RAGError, configured_value, load_rag_settings
from .adr import (
    approval_history as get_approval_history,
    create_proposals,
    index_document_text,
    list_adrs,
    load_adr,
    markdown_path as adr_markdown_path,
    metadata_for as adr_metadata,
    transition as transition_adr,
    update_indexing,
    validate_record as validate_adr_record,
)
from .evaluation import RUBRIC_VERSION, validate_evaluation
import hashlib

ROOT = Path.cwd()
DATA = ROOT / ".kataliarc"
FILES: dict[str, Any] = {
    "context.json": {"business_goals": [], "business_requirements": [], "constraints": [], "quality_attributes": [], "quality_scenarios": [], "references": []},
    "utility-tree.json": {"quality_attributes": []},
    "tactics.json": {"scenario_arguments": [], "tactics": [], "pattern_tactic_interactions": [], "tactic_interactions": [], "alternatives": []},
    "evaluation.json": {"rubric_version": RUBRIC_VERSION, "assessments": [], "comparison": {"constraints": [], "dominance": [], "tradeoffs": [], "recommendation": None}, "risks": [], "sensitivity_points": [], "tradeoffs": [], "iteration": 0, "iteration_requests": [], "iteration_history": [], "assessment_history": []},
    "review.json": {"objections": []},
    "decision.json": {"selected_alternative_id": None, "status": "indeterminado", "tradeoffs": [], "risks": [], "unresolved_questions": [], "rationale": ""},
}
MD_FILES = {
    "context.md": "# Contexto\n\nDescribe aquí el problema, objetivos y contexto proporcionados por el cliente.\n",
    "utility-tree.md": "# Árbol de utilidad\n\nPrioridades A/M/B pendientes de confirmación del cliente representante.\n",
    "tactics.md": "# Tácticas y argumentos\n\nCompleta los argumentos y condiciones para todos los escenarios.\n",
    "alternatives.md": "# Alternativas arquitectónicas\n\nDescribe ensamblados, patrones, tácticas y adaptaciones estructurales.\n",
    "evaluation.md": "# Evaluación cualitativa\n\nContribución y cumplimiento se valoran por separado.\n",
    "review.md": "# Revisión crítica\n\nObjeciones y correcciones sugeridas.\n",
    "decision.md": "# Decisión\n\nEstado inicial: indeterminado.\n",
    "decisions/ADR-001.md": "# ADR-001: Decisión arquitectónica\n\n- Estado: propuesto\n- Contexto: pendiente\n- Decisión: pendiente\n- Alternativas: pendiente\n- Trade-offs y riesgos: pendiente\n- Información/validación pendiente: pendiente\n",
}
MD_FILES_EN = {
    "context.md": "# Context\n\nDescribe the problem, goals, and context provided by the client.\n",
    "utility-tree.md": "# Utility tree\n\nA/M/B priorities pending confirmation by the client representative.\n",
    "tactics.md": "# Tactics and arguments\n\nComplete the arguments and conditions for every scenario.\n",
    "alternatives.md": "# Architectural alternatives\n\nDescribe assemblies, patterns, tactics, and structural adaptations.\n",
    "evaluation.md": "# Qualitative evaluation\n\nContribution and compliance are assessed separately.\n",
    "review.md": "# Critical review\n\nObjections and suggested corrections.\n",
    "decision.md": "# Decision\n\nInitial status: undetermined.\n",
    "decisions/ADR-001.md": "# ADR-001: Architecture decision\n\n- Status: proposed\n- Context: pending\n- Decision: pending\n- Alternatives: pending\n- Trade-offs and risks: pending\n- Pending information/validation: pending\n",
}


def write_new(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return False
    path.write_text(content, encoding="utf-8")
    return True


def write_json(path: Path, data: Any) -> bool:
    return write_new(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def init(agent: str, project: Path | None = None, *, overwrite: bool = False, interactive: bool = False, no_banner: bool = False, no_music: bool = False, confirm: bool = True, language: str | None = None, global_scope: bool = False, rag_vector_store_id: str | None = None) -> int:
    global ROOT, DATA
    ROOT = (project or Path.cwd()).resolve()
    DATA = ROOT / ".kataliarc"
    show_banner = not no_banner and (interactive or getattr(sys.stdout, "isatty", lambda: False)())
    if show_banner:
        clear_terminal()
    render_banner(enabled=show_banner)
    if not no_music and getattr(sys.stdout, "isatty", lambda: False)():
        play_retro_music()
    was_initialized = DATA.exists()
    if language is None:
        try:
            language = json.loads((DATA / "config.json").read_text(encoding="utf-8")).get("language", "es")
        except (OSError, json.JSONDecodeError):
            language = "es"
    if was_initialized and interactive:
        print("KatalIArc ya está inicializado; se conservarán los artefactos existentes." if language == "es" else "KatalIArc is already initialized; existing artifacts will be preserved.")
    if interactive:
        try:
            agent = select_agent()
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        selected = dict(AGENTS)[agent]
        location = select_choice("Installation location:", [
            ("project", "Current project"),
            ("directory", "Another project directory"),
            ("global", "Global user installation"),
        ])
        if location == "directory":
            proposed = input(f"Project directory [{ROOT}]: ").strip()
            if proposed:
                ROOT = Path(proposed).expanduser().resolve()
        elif location == "global":
            ROOT = Path.home().resolve()
            global_scope = True
        if location in {"directory", "global"}:
            DATA = ROOT / ".kataliarc"
        try:
            language = select_language()
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print("\nKatalIArc Installation\n")
        print(f"Agent          : {selected}\nLocation       : {'Global user installation' if global_scope else ROOT}\nLanguage       : {'Spanish' if language == 'es' else 'English'}\nSkills         : Pohl, Toulmin, Walton")
        proceed = select_choice("Proceed with installation?", [("yes", "Yes"), ("no", "No")], default=0) if confirm else "yes"
        if proceed != "yes":
            print("Inicialización cancelada.")
            return 0
    if agent not in ADAPTERS:
        print(f"Proveedor no soportado: {agent}", file=sys.stderr)
        return 2
    if ROOT.exists() and not ROOT.is_dir():
        print(f"La ruta del proyecto no es un directorio: {ROOT}", file=sys.stderr)
        return 2
    show_progress = interactive and getattr(sys.stdout, "isatty", lambda: False)()
    progress_labels = ["Metamodelo", "Flujo de trabajo", "Agentes", "Rúbrica y schemas"]

    def progress(step: int) -> None:
        if not show_progress:
            return
        width = 18
        bar = "█" * width
        color = "\033[36m" if "NO_COLOR" not in __import__("os").environ else ""
        reset = "\033[0m" if color else ""
        label = progress_labels[step - 1]
        sys.stdout.write(f"{color}{bar}{reset} 100%  {label} — OK\n")
        sys.stdout.flush()
    if show_progress:
        # prompt_toolkit can leave the cursor on its final hint line after Enter.
        sys.stdout.write("\nInstalando KatalIArc...\n")
        sys.stdout.flush()
    ROOT.mkdir(parents=True, exist_ok=True)
    adapter = get_adapter(agent)
    if global_scope:
        adapter.configure_global()
    created = []
    try:
        for name, data in FILES.items():
            if write_json(DATA / name, data):
                created.append(str(DATA / name))
        for name, text in (MD_FILES_EN if language == "en" else MD_FILES).items():
            if write_new(DATA / name, text):
                created.append(str(DATA / name))
        package_root = Path(__file__).resolve().parent / "resources"
        installed_resource_paths = []
        for dirname, resources in (("schemas", package_root / "schemas"), ("metamodel", package_root / "metamodel")):
            for item in resources.glob("*"):
                target = DATA / dirname / item.name
                if item.is_file() and write_new(target, item.read_text(encoding="utf-8")):
                    created.append(str(target))
                    installed_resource_paths.append(target)
        progress(1)
        progress(2)
        installed_adapter_paths = adapter.install(ROOT, Path(__file__).resolve().parent, overwrite=overwrite)
        created.extend(str(path) for path in installed_adapter_paths)
        progress(3)
        config = DATA / "config.json"
        previous = {}
        if config.exists():
            try:
                previous = json.loads(config.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                if not overwrite:
                    raise ValueError(f"Configuración existente inválida: {config}; usa --update para reemplazarla")
        current = {**previous, "agent": agent, "language": language or "es", "version": "0.2.0", "scope": "user" if global_scope else "project", "project_id": previous.get("project_id") or str(uuid.uuid4())}
        if rag_vector_store_id:
            prior_rag = previous.get("rag", {}) if isinstance(previous.get("rag", {}), dict) else {}
            current["rag"] = {**prior_rag, "enabled": True, "vector_store_id": rag_vector_store_id}
        if not config.exists() or overwrite or current != previous:
            config.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            created.append(str(config))
        managed = {}
        # Record installed integration resources with a content hash. User artifacts are intentionally excluded.
        for relative in list(adapter.instruction_files) + list(adapter.extra_files):
            path = ROOT / relative
            if path.is_file() and path in installed_adapter_paths:
                managed[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        for skill in ("pohl", "toulmin", "walton"):
            relative = f"{adapter.skill_root}/kataliarc-{skill}/SKILL.md"
            path = ROOT / relative
            if path.is_file() and path in installed_adapter_paths:
                managed[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ("schemas", "metamodel"):
            for path in (DATA / folder).glob("*"):
                if path.is_file() and path in installed_resource_paths:
                    relative = str(path.relative_to(ROOT))
                    managed[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = DATA / MANIFEST
        if not manifest.exists():
            manifest.write_text(json.dumps({"version": "0.2.0", "files": managed}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        elif overwrite:
            prior = load_json(manifest)
            prior["version"] = "0.2.0"
            prior["files"].update({k: v for k, v in managed.items() if k not in prior["files"]})
            manifest.write_text(json.dumps(prior, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        progress(4)
    except (OSError, ValueError, KeyError) as exc:
        if show_progress:
            sys.stdout.write("\n")
        print(f"No se pudo completar la instalación: {exc}", file=sys.stderr)
        return 2
    executable = __import__("shutil").which(adapter.executable)
    if not executable:
        print(f"Aviso: no se encontró {adapter.executable} en PATH. KatalIArc quedó instalado, pero esa herramienta externa debe instalarse por separado.")
    validation_errors = []
    for required in [*FILES, *MD_FILES_EN, "config.json"]:
        if not (DATA / required).is_file():
            validation_errors.append(f"falta {DATA / required}")
    config_data = load_json(DATA / "config.json")
    if config_data.get("agent") not in ADAPTERS or config_data.get("language") not in {"es", "en"}:
        validation_errors.append("config.json contiene agente o idioma inválido")
    schema_dir = Path(__file__).resolve().parent / "resources" / "schemas"
    for schema_name in ("context.schema.json", "utility-tree.schema.json", "tactics.schema.json", "evaluation.schema.json", "adr.schema.json"):
        schema_path = schema_dir / schema_name
        try:
            if not isinstance(load_json(schema_path), dict):
                validation_errors.append(f"schema inválido: {schema_path}")
        except ValueError as exc:
            validation_errors.append(str(exc))
    if validation_errors:
        if show_progress:
            sys.stdout.write("\n")
        print("Validación de instalación fallida: " + "; ".join(validation_errors), file=sys.stderr)
        return 2
    if show_progress:
        print("████████████████████████ 100% instalado")
        print("Todo está OK.")
    print(f"Inicialización lista ({len(created)} archivos nuevos o actualizados). Proyecto: {DATA}")
    print("Validación de instalación correcta: rutas y configuración comprobadas.")
    print("Commands: kataliarc pohl elicit|prioritize, toulmin design, walton evaluate|review|decide, decide --help, validate, status")
    print(f"Comienza con: kataliarc pohl elicit (agente seleccionado: {adapter.label})")
    if show_progress:
        input("Presiona Enter para continuar...")
    return 0


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def validate() -> int:
    errors: list[str] = []
    legacy_utility_tree = False
    for name in FILES:
        p = DATA / name
        try:
            data = load_json(p)
            if not isinstance(data, dict):
                errors.append(f"{p}: se esperaba un objeto JSON")
        except ValueError as exc:
            errors.append(str(exc))
    if not errors and (DATA / "context.json").exists():
        context = load_json(DATA / "context.json")
        for key in FILES["context.json"]:
            if not isinstance(context.get(key), list):
                errors.append(f"context.json: {key} debe ser una lista")
        scenarios = context.get("quality_scenarios", [])
        ids = [s.get("id") for s in scenarios if isinstance(s, dict)]
        valid = set(ids)
        scenarios_by_id = {str(s.get("id")): s for s in scenarios if isinstance(s, dict) and s.get("id")}
        if len(ids) != len(set(ids)):
            errors.append("context.json: ids de escenario duplicados")
        for scenario in scenarios:
            if not isinstance(scenario, dict):
                errors.append("context.json: cada quality_scenario debe ser un objeto")
                continue
            for field in ("id", "description", "quality_attribute", "priority", "mandatory"):
                if field not in scenario:
                    errors.append(f"context.json: escenario sin campo {field}")
            if scenario.get("priority", "pendiente") not in {"A", "M", "B", "pendiente"}:
                errors.append(f"{scenario.get('id')}: prioridad debe ser A, M, B o pendiente")
        utility = load_json(DATA / "utility-tree.json")
        branches = utility.get("quality_attributes", [])
        if not isinstance(branches, list):
            errors.append("utility-tree.json: quality_attributes debe ser una lista")
        else:
            seen_references = set()
            for branch in branches:
                if not isinstance(branch, dict):
                    errors.append("utility-tree.json: each quality attribute branch must be an object")
                    continue
                branch_name = branch.get("name") or branch.get("quality_attribute") or branch.get("attribute")
                if not isinstance(branch_name, str):
                    errors.append("utility-tree.json: each branch must contain its quality-attribute name")
                    continue
                scenario_ids = branch.get("scenario_ids")
                if not isinstance(scenario_ids, list):
                    legacy_scenarios = branch.get("scenarios")
                    if isinstance(legacy_scenarios, list):
                        legacy_utility_tree = True
                        scenario_ids = [item.get("id") for item in legacy_scenarios if isinstance(item, dict)]
                    else:
                        errors.append("utility-tree.json: each branch must contain scenario_ids as a list")
                        continue
                for scenario_id in scenario_ids:
                    if not isinstance(scenario_id, str):
                        errors.append("utility-tree.json: scenario IDs must be strings")
                        continue
                    if scenario_id not in valid:
                        errors.append(f"utility-tree.json: referencia a escenario inexistente {scenario_id}")
                    elif scenarios_by_id[str(scenario_id)].get("quality_attribute") != branch_name:
                        errors.append(f"utility-tree.json: escenario {scenario_id} está bajo un atributo de calidad distinto")
                    if scenario_id in seen_references:
                        errors.append(f"utility-tree.json: referencia duplicada a escenario {scenario_id}")
                    seen_references.add(scenario_id)
        tactic_data = load_json(DATA / "tactics.json")
        for key in FILES["tactics.json"]:
            if not isinstance(tactic_data.get(key), list):
                errors.append(f"tactics.json: {key} debe ser una lista")
        for arg in tactic_data.get("scenario_arguments", []):
            sid = arg.get("scenario_id")
            if sid not in valid:
                errors.append(f"tactics.json: argumento refiere escenario inexistente {sid}")
            for key in ("claim", "grounds", "warrant", "backing", "qualifier", "rebuttal"):
                if key not in arg:
                    errors.append(f"tactics.json: argumento de {sid} no contiene {key}")
        evaluation = load_json(DATA / "evaluation.json")
        tactics = load_json(DATA / "tactics.json")
        if evaluation.get("assessments") or tactics.get("alternatives"):
            errors.extend(validate_evaluation(evaluation, context, tactics, utility))
    decisions_dir = DATA / "decisions"
    for path in decisions_dir.glob("ADR-*.json") if decisions_dir.is_dir() else []:
        try:
            validate_adr_record(load_json(path))
        except ValueError as exc:
            errors.append(f"{path}: {exc}")
    if errors:
        print("Validación fallida:", file=sys.stderr)
        print("\n".join(f"- {e}" for e in errors), file=sys.stderr)
        return 1
    print("Validación correcta: JSON legible, estructura base y referencias comprobadas.")
    if legacy_utility_tree:
        print("Migration note: utility-tree.json still contains copied scenarios. Run 'kataliarc pohl prioritize' to convert branches to scenario_ids; context.json remains the source of truth.")
    return 0


PROMPTS = {
    "elicit": "Lee context.md y completa context.json solo con información proporcionada. Marca incertidumbre y no inventes requisitos.",
    "prioritize": "Actualiza la prioridad en context.json solo cuando el cliente la haya confirmado. Organiza utility-tree.json como ramas por atributo con scenario_ids únicamente; si encuentras el formato antiguo con escenarios copiados, conviértelo preservando sus IDs y orden. No copies descripciones, restricciones ni prioridades. No asignes prioridad A/M/B si no está confirmada.",
    "design": "Desde todos los escenarios propone tácticas, argumentos Toulmin, interacciones y 2-3 alternativas ensambladas. Distingue hipótesis de evidencia.",
    "evaluate": "Aplica los mecanismos Walton M1-M4. Lee .kataliarc/metamodel/walton-rubric.json; evalúa cada alternativa completa contra cada escenario del utility tree. Escribe evaluation.json y evaluation.md con assessments pareados y completos, etiquetas y cumplimiento separados, justificación causal, riesgos, puntos de sensibilidad y trade-offs trazables. Si hace falta trabajo de Toulmin, agrega iteration_requests con referencias válidas. No inventes métricas, evidencia ni cumplimiento.",
    "review": "Aplica una segunda pasada de preguntas críticas Walton a cada evaluación y afirmación causal. Registra critical_question_assessments, objeciones y contraargumentos; corrige evaluaciones fundamentadamente conservando el historial. Completa review.json con decision_proposals si son independientes. No aceptes ni indexes el ADR.",
    "decide": "Integra evaluación y revisión crítica; recomienda decisión definitiva, provisional o indeterminada con trade-offs, riesgos, condiciones y pendientes. No aceptes el ADR.",
}
PROMPTS_EN = {
    "elicit": "Read context.md and complete context.json only from provided information. Mark uncertainty; do not invent requirements.",
    "prioritize": "Update scenario priorities in context.json only when the client has confirmed them. Build utility-tree.json as quality-attribute branches containing scenario_ids only; if the legacy format with copied scenarios exists, convert it while preserving IDs and ordering. Do not copy descriptions, constraints, or priorities. Do not assign A/M/B unless confirmed.",
    "design": "From all scenarios, propose tactics, Toulmin arguments, interactions, and 2-3 assembled alternatives. Distinguish hypotheses from evidence.",
    "evaluate": "Act as Walton and apply mechanisms M1-M4. Read .kataliarc/metamodel/walton-rubric.json. Evaluate each complete alternative against every scenario referenced by the utility tree. Write evaluation.json and evaluation.md with complete alternative/scenario pairs, separately classified contribution and compliance, causal justification, traceable ATAM risks, sensitivity points, and trade-offs. If Toulmin work is needed, add iteration_requests with valid references. Never invent metrics, thresholds, evidence, or compliance.",
    "review": "Act as Walton in a second critical-review pass. Apply explicit Walton question schemes from .kataliarc/metamodel/walton-rubric.json to claims and scenario assessments. Record critical_question_assessments with scheme, question, claim_ref, answer, result, evidence_refs, and objection. Correct a classification only when a premise/evidence issue justifies it; preserve the previous assessment in assessment_history and log the revision. Update review.json with summary, questions, objections, and independent decision_proposals. Never accept or index an ADR.",
    "decide": "Act as Walton. Integrate the revised evaluation and critical review; recommend a final, provisional, or indeterminate outcome with rationale, trade-offs, risks, limitations, and open questions. Do not mark an ADR accepted.",
}
ROLE_ACTIONS = {
    "pohl": ("elicit", "prioritize"),
    "toulmin": ("design",),
    "walton": ("evaluate", "review", "decide"),
}


def run_stage(stage: str, with_agent: bool, *, repository: Path | None = None, rag_enabled: bool = True, provider_override: str | None = None) -> int:
    if not DATA.exists():
        print("No existe .kataliarc/. Ejecuta kataliarc init --agent codex.", file=sys.stderr)
        return 2
    if with_agent:
        agent = provider_override or "codex"
        if provider_override is None:
            try:
                agent = json.loads((DATA / "config.json").read_text(encoding="utf-8")).get("agent", agent)
            except (OSError, json.JSONDecodeError):
                pass
        try:
            language = json.loads((DATA / "config.json").read_text(encoding="utf-8")).get("language", "es")
        except (OSError, json.JSONDecodeError):
            language = "es"
        prompts = PROMPTS_EN if language == "en" else PROMPTS
        prompt = prompts[stage]
        if stage == "design":
            config = {}
            try:
                config = json.loads((DATA / "config.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
            rag_config = config.get("rag", {}) if isinstance(config.get("rag", {}), dict) else {}
            config = {**config, "rag": {**rag_config, "enabled": rag_enabled and rag_config.get("enabled", True)}}
            try:
                input_data = build_toulmin_input(DATA, repository or ROOT, config)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"Could not analyze the repository for Toulmin: {exc}", file=sys.stderr)
                return 2
            analysis_path = DATA / "repository-analysis.json"
            input_path = DATA / "toulmin-input.json"
            try:
                write_managed_json(analysis_path, input_data["repository"])
                write_managed_json(input_path, input_data)
            except (OSError, ValueError) as exc:
                print(f"Could not prepare the Toulmin input: {exc}", file=sys.stderr)
                return 2
            prompt = build_design_prompt(input_path, language)
            retrieval = input_data["rag"]
            print(f"Repository analysis: {len(input_data['repository'].get('findings', []))} findings; RAG: {retrieval['status']}.")
            for warning in retrieval["warnings"]:
                print(f"RAG warning: {warning}", file=sys.stderr)
        provider = AgentProvider()
        result = provider.run(agent, prompt, ROOT)
        if result.error:
            print(result.error, file=sys.stderr)
        if result.returncode == 0 and stage in {"evaluate", "review", "decide"}:
            try:
                context = load_json(DATA / "context.json")
                tactics = load_json(DATA / "tactics.json")
                utility = load_json(DATA / "utility-tree.json")
                evaluation = load_json(DATA / "evaluation.json")
                if evaluation.get("assessments") or tactics.get("alternatives"):
                    errors = validate_evaluation(evaluation, context, tactics, utility)
                    if errors:
                        print("Walton evaluation validation failed: " + "; ".join(errors), file=sys.stderr)
                        return 1
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"Could not validate Walton evaluation: {exc}", file=sys.stderr)
                return 1
        if result.returncode == 0 and stage == "evaluate":
            try:
                config = load_json(DATA / "config.json")
            except ValueError:
                config = {}
            walton_config = config.get("walton", {}) if isinstance(config.get("walton", {}), dict) else {}
            try:
                max_iterations = max(0, min(5, int(walton_config.get("max_iterations", 3))))
            except (TypeError, ValueError):
                max_iterations = 3
            for iteration in range(1, max_iterations + 1):
                evaluation = load_json(DATA / "evaluation.json")
                requests = [item for item in evaluation.get("iteration_requests", []) if isinstance(item, dict) and item.get("status", "PENDING") == "PENDING"]
                if not requests:
                    break
                previous_assessments = evaluation.get("assessments", [])
                refinement_prompt = (
                    f"{prompts['design']}\n\nWalton requested a bounded refinement. Use ONLY these requests: "
                    f"{json.dumps(requests, ensure_ascii=False, indent=2)}\n"
                    "Revise candidate tactics, combinations or Toulmin arguments in tactics.json and alternatives.md. "
                    "Do not edit evaluation.json, claim validation, inspect external repositories, or accept an ADR."
                )
                refined = provider.run(agent, refinement_prompt, ROOT)
                if refined.returncode != 0:
                    print(refined.error or "Toulmin refinement failed.", file=sys.stderr)
                    for request in requests:
                        request["status"] = "UNRESOLVED"
                    evaluation["iteration_requests"] = requests
                    evaluation.setdefault("iteration_history", []).append({"iteration": iteration, "action": "toulmin_refinement", "observation": refined.error or "Provider returned failure", "source_artifacts": ["evaluation.json"], "outcome": "UNRESOLVED", "previous_assessments": previous_assessments})
                    evaluation["iteration"] = iteration
                    (DATA / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    return refined.returncode
                for request in requests:
                    request["status"] = "RESOLVED"
                evaluation["iteration_requests"] = requests
                evaluation.setdefault("iteration_history", []).append({"iteration": iteration, "action": "toulmin_refinement", "observation": "Toulmin revised requested artifacts; Walton reevaluation follows.", "source_artifacts": ["tactics.json", "alternatives.md"], "outcome": "REFINED", "previous_assessments": previous_assessments})
                evaluation["iteration"] = iteration
                evaluation.setdefault("assessment_history", []).append({"iteration": iteration - 1, "assessments": previous_assessments})
                (DATA / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                prior_iteration_history = list(evaluation.get("iteration_history", []))
                prior_assessment_history = list(evaluation.get("assessment_history", []))
                reevaluate = provider.run(agent, prompts["evaluate"], ROOT)
                if reevaluate.returncode != 0:
                    print(reevaluate.error or "Walton reevaluation failed.", file=sys.stderr)
                    return reevaluate.returncode
                current = load_json(DATA / "evaluation.json")
                current["iteration_history"] = prior_iteration_history + [entry for entry in current.get("iteration_history", []) if entry not in prior_iteration_history]
                current["assessment_history"] = prior_assessment_history + [entry for entry in current.get("assessment_history", []) if entry not in prior_assessment_history]
                current["iteration"] = iteration
                (DATA / "evaluation.json").write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                errors = validate_evaluation(current, load_json(DATA / "context.json"), load_json(DATA / "tactics.json"), load_json(DATA / "utility-tree.json"))
                if errors:
                    print("Walton reevaluation validation failed: " + "; ".join(errors), file=sys.stderr)
                    return 1
            final_evaluation = load_json(DATA / "evaluation.json")
            pending = [request for request in final_evaluation.get("iteration_requests", []) if isinstance(request, dict) and request.get("status", "PENDING") == "PENDING"]
            if pending:
                for request in pending:
                    request["status"] = "UNRESOLVED"
                final_evaluation.setdefault("iteration_history", []).append({"iteration": max_iterations, "action": "iteration_limit", "observation": "Walton refinement limit reached; remaining requests require manual follow-up.", "source_artifacts": ["evaluation.json"], "outcome": "UNRESOLVED"})
                (DATA / "evaluation.json").write_text(json.dumps(final_evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if max_iterations == 0:
                evaluation = load_json(DATA / "evaluation.json")
                for request in evaluation.get("iteration_requests", []):
                    if isinstance(request, dict) and request.get("status", "PENDING") == "PENDING":
                        request["status"] = "UNRESOLVED"
                (DATA / "evaluation.json").write_text(json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if result.returncode == 0 and stage == "review":
            try:
                proposals = create_proposals(DATA)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"Could not persist Walton's ADR proposal: {exc}", file=sys.stderr)
                return 1
            for proposal in proposals:
                print(f"ADR proposal saved: {adr_markdown_path(DATA, proposal['adr_id'])} (PROPOSED, v{proposal['current_version']['version']}).")
        return result.returncode
    if stage == "elicit":
        print("Edita .kataliarc/context.md y context.json con datos confirmados por el cliente.")
    elif stage == "prioritize":
        print("Update confirmed priorities in context.json; keep utility-tree.json as ID references only.")
    else:
        outputs = {"design": ["tactics.json", "tactics.md", "alternatives.md"], "evaluate": ["evaluation.json", "evaluation.md"], "review": ["review.json", "review.md"], "decide": ["decision.json", "decision.md", "decisions/ADR-001.md"]}[stage]
        print(f"Completa artefactos de {stage}: " + ", ".join(str(DATA / x) for x in outputs))
    return 0


def status() -> int:
    if not DATA.exists():
        print("Proyecto no inicializado. Ejecuta kataliarc init --agent codex.")
        return 1
    for name in [*FILES, *MD_FILES]:
        p = DATA / name
        print(f"{'ok' if p.exists() else 'pendiente'}  {p}")
    scenarios = []
    try:
        scenarios = load_json(DATA / "context.json").get("quality_scenarios", [])
    except ValueError:
        pass
    waiting = [s.get("id", "?") for s in scenarios if s.get("priority", "pendiente") == "pendiente"]
    if waiting:
        print("Prioridad pendiente (confirmación del cliente): " + ", ".join(waiting))
    for record in list_adrs(DATA):
        print(f"ADR {record['adr_id']}  {record['status']}  v{record['current_version']['version']}  RAG:{record.get('indexing', {}).get('status', 'NOT_REQUESTED')}")
    return 0


def rag_test(query: str, max_results: int = 3) -> int:
    """Make exactly one read-only search request to the configured ADR vector store."""
    config_path = DATA / "config.json"
    try:
        config = load_json(config_path)
    except ValueError as exc:
        print(f"Could not load KatalIArc configuration: {exc}", file=sys.stderr)
        return 2
    rag_config = config.get("rag", {}) if isinstance(config.get("rag", {}), dict) else {}
    if rag_config.get("enabled") is False:
        print("RAG is disabled in .kataliarc/config.json.", file=sys.stderr)
        return 2
    settings = load_rag_settings(config, DATA.parent)
    if not settings["vector_store_id"]:
        print("No vector store ID configured. Set OPENAI_VECTOR_STORE_ID or run init with --rag-vector-store-id.", file=sys.stderr)
        return 2
    api_key = configured_value("OPENAI_API_KEY", DATA.parent)
    if not api_key:
        print("OPENAI_API_KEY is not configured in the environment or project .env file.", file=sys.stderr)
        return 2
    if not 1 <= max_results <= 5:
        print("--max-results must be between 1 and 5 for a connection check.", file=sys.stderr)
        return 2
    try:
        results = OpenAIVectorStoreRetriever(api_key, settings["vector_store_id"]).search(query, max_results=max_results)
    except (RAGError, ValueError) as exc:
        print(f"Vector store search failed: {exc}", file=sys.stderr)
        return 1
    print(f"Vector store search succeeded; {len(results)} result(s).")
    for index, result in enumerate(results, 1):
        source = result.get("adr_id") or result.get("filename") or result.get("file_id") or "source unavailable"
        source = "".join(character for character in str(source) if character.isprintable()).replace("\n", " ").replace("\r", " ")
        score = result.get("score")
        score_text = f" (score: {score})" if score is not None else ""
        print(f"{index}. {source}{score_text}")
    if not results:
        print("The request succeeded, but no text chunks matched this query.")
    return 0


def _adr_actor(value: str | None) -> str:
    return value.strip() if value and value.strip() else getpass.getuser()


def _project_id() -> str:
    path = DATA / "config.json"
    config = load_json(path)
    project_id = config.get("project_id")
    if not project_id:
        project_id = str(uuid.uuid4())
        config["project_id"] = project_id
        path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(project_id)


def _index_accepted_adr(adr_id: str) -> int:
    """Background worker: index only after local acceptance is already durable."""
    try:
        record = load_adr(DATA, adr_id)
        validate_adr_record(record)
        if record["status"] != "ACCEPTED":
            raise ValueError("Only ACCEPTED ADRs can be indexed.")
        config = load_json(DATA / "config.json")
        settings = load_rag_settings(config, DATA.parent)
        if not settings.get("vector_store_id"):
            raise RAGError("No vector store ID is configured.")
        api_key = configured_value("OPENAI_API_KEY", DATA.parent)
        if not api_key:
            raise RAGError("OPENAI_API_KEY is not configured.")
        update_indexing(DATA, adr_id, "PENDING")
        update_indexing(DATA, adr_id, "INDEXING")
        record = load_adr(DATA, adr_id)
        metadata = adr_metadata(record, _project_id())
        retriever = OpenAIVectorStoreRetriever(api_key, settings["vector_store_id"])
        filename = f"kataliarc-{record['adr_id']}-v{record['current_version']['version']}.md"

        def remember_file(file_id: str) -> None:
            update_indexing(DATA, adr_id, "INDEXING", file_id=file_id)

        result = retriever.index_accepted_adr(
            filename=filename,
            document=index_document_text(record),
            attributes=metadata,
            existing_file_id=record.get("indexing", {}).get("file_id"),
            on_uploaded=remember_file,
        )
        update_indexing(DATA, adr_id, "INDEXED", file_id=result["file_id"], remote={"file_id": result["file_id"], "vector_store_id": settings["vector_store_id"], "index_key": metadata["index_key"], "indexed_at": datetime.now(timezone.utc).isoformat()})
        print(f"{adr_id} remains ACCEPTED; indexing is INDEXED ({result['file_id']}).")
        return 0
    except (OSError, ValueError, RAGError) as exc:
        try:
            current = load_adr(DATA, adr_id)
            if current.get("status") == "ACCEPTED":
                update_indexing(DATA, adr_id, "FAILED", detail=str(exc))
        except (OSError, ValueError):
            pass
        print(f"{adr_id} acceptance is retained; indexing FAILED: {exc}", file=sys.stderr)
        return 1


def _queue_adr_indexing(adr_id: str, *, supersedes: str | None = None) -> int:
    """Launch a detached worker and return without waiting for remote vectorization."""
    try:
        record = load_adr(DATA, adr_id)
        if record.get("status") != "ACCEPTED":
            raise ValueError("Only ACCEPTED ADRs can be queued for indexing.")
        update_indexing(DATA, adr_id, "PENDING", detail="Asynchronous indexing worker queued.")
        command = [sys.executable, "-m", "kataliarc.cli", "--index-adr-worker", adr_id]
        if supersedes:
            command.extend(("--supersede-adr-worker", supersedes))
        subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"{adr_id} is ACCEPTED; asynchronous indexing started (PENDING).")
        return 0
    except (OSError, ValueError) as exc:
        try:
            record = load_adr(DATA, adr_id)
            if record.get("status") == "ACCEPTED":
                update_indexing(DATA, adr_id, "FAILED", detail=f"Could not start asynchronous index worker: {exc}")
        except (OSError, ValueError):
            pass
        print(f"{adr_id} approval is retained; indexing worker could not start: {exc}", file=sys.stderr)
        return 1


def _supersede_remote(adr_id: str) -> None:
    """Mark a superseded local ADR in remote metadata when possible."""
    record = load_adr(DATA, adr_id)
    resources = record.get("indexing", {}).get("remote_resources", [])
    if not resources:
        return
    try:
        config = load_json(DATA / "config.json")
        settings = load_rag_settings(config, DATA.parent)
        api_key = configured_value("OPENAI_API_KEY", DATA.parent)
        if not api_key or not settings.get("vector_store_id"):
            raise RAGError("RAG credentials or vector store are not configured.")
        retriever = OpenAIVectorStoreRetriever(api_key, settings["vector_store_id"])
        attrs = adr_metadata(record, str(config.get("project_id", "unknown")))
        for item in resources:
            updated = retriever.update_attributes(item["file_id"], attrs)
            if not isinstance(updated.get("attributes"), dict) or updated["attributes"].get("decision_status") != "SUPERSEDED":
                raise RAGError("Remote ADR status update was not confirmed.")
    except (OSError, ValueError, RAGError) as exc:
        update_indexing(DATA, adr_id, "FAILED", detail=f"ADR is superseded locally; remote status update failed: {exc}")
        print(f"Warning: {adr_id} is SUPERSEDED locally, but remote retrieval metadata could not be updated.", file=sys.stderr)


def decide_action(*, show: str | None = None, accept: str | None = None, reject: str | None = None, request_changes: str | None = None, history: str | None = None, retry_index: str | None = None, actor: str | None = None, note: str = "", supersedes: str | None = None) -> int:
    selected = [("show", show), ("accept", accept), ("reject", reject), ("request changes", request_changes), ("history", history), ("retry index", retry_index)]
    actions = [(name, value) for name, value in selected if value]
    if len(actions) != 1:
        print("Choose exactly one ADR action.", file=sys.stderr)
        return 2
    action, adr_id = actions[0]
    try:
        if action == "show":
            record = load_adr(DATA, adr_id)
            validate_adr_record(record)
            print(json.dumps({"adr_id": record["adr_id"], "status": record["status"], "version": record["current_version"]["version"], "indexing": record["indexing"], "markdown": str(adr_markdown_path(DATA, adr_id))}, indent=2, ensure_ascii=False))
            return 0
        if action == "history":
            record = load_adr(DATA, adr_id)
            print(json.dumps({
                "lifecycle": get_approval_history(DATA, adr_id),
                "approvals": record.get("approval_history", []),
                "versions": [{"version": item.get("version"), "title": item.get("title"), "created_at": item.get("created_at")} for item in record.get("versions", [])],
                "indexing_attempts": record.get("indexing", {}).get("attempts", []),
            }, indent=2, ensure_ascii=False))
            return 0
        if action == "retry index":
            record = load_adr(DATA, adr_id)
            if record.get("status") != "ACCEPTED":
                raise ValueError("Only ACCEPTED ADRs can be reindexed.")
            if record.get("indexing", {}).get("status") == "INDEXED":
                print(f"{adr_id} is already INDEXED; no duplicate was created.")
                return 0
            return _queue_adr_indexing(adr_id, supersedes=record.get("supersedes"))
        op = {"accept": "accept", "reject": "reject", "request changes": "request-changes"}[action]
        if op == "request-changes" and not note.strip():
            raise ValueError("Provide feedback with --note when requesting changes.")
        old_adr = supersedes
        if op == "accept" and old_adr:
            old_adr = old_adr.upper()
        record = transition_adr(DATA, adr_id, op, actor=_adr_actor(actor), note=note, supersedes=old_adr)
        print(f"{record['adr_id']} v{record['current_version']['version']}: {record['status']}.")
        if op == "accept":
            return _queue_adr_indexing(adr_id, supersedes=old_adr)
        return 0
    except (OSError, ValueError) as exc:
        print(f"ADR action failed: {exc}", file=sys.stderr)
        return 2


def build_public_help_parser() -> argparse.ArgumentParser:
    """Build the concise, user-facing help view with standard argparse formatting."""
    parser = argparse.ArgumentParser(
        prog="kataliarc help",
        description="Flujo local de apoyo a decisiones de arquitectura",
    )
    commands = parser.add_subparsers(dest="command")
    help_rows = (
        ("init", "Inicializa artefactos y skills del proyecto"),
        ("help", "Muestra los comandos disponibles"),
        ("pohl elicit", "Recoge contexto y escenarios"),
        ("pohl prioritize", "Organiza prioridades confirmadas"),
        ("toulmin design", "Propone tácticas y alternativas"),
        ("walton evaluate", "Evalúa escenarios, alternativas y trade-offs"),
        ("walton review", "Revisa críticamente los argumentos"),
        ("walton decide", "Integra hallazgos y recomienda un resultado"),
    )
    for command, description in help_rows:
        commands.add_parser(command, help=description)
    return parser


def build_parser() -> argparse.ArgumentParser:
    class KatalIArcParser(argparse.ArgumentParser):
        def format_help(self) -> str:
            if self.prog == "kataliarc":
                return build_public_help_parser().format_help()
            return super().format_help()

    parser = KatalIArcParser(
        prog="kataliarc",
        description="Flujo local de apoyo a decisiones de arquitectura",
    )
    parser.add_argument("--index-adr-worker", metavar="ADR_ID", help=argparse.SUPPRESS)
    parser.add_argument("--supersede-adr-worker", metavar="ADR_ID", help=argparse.SUPPRESS)
    parser.add_argument("--init", "-init", dest="command", action="store_const", const="init", help="Inicia el asistente de configuración")
    subs = parser.add_subparsers(dest="command")
    p = subs.add_parser("init", help="Inicializa artefactos y skills del proyecto")
    p.add_argument("--agent", choices=["codex", "claude", "gemini", "copilot"])
    p.add_argument("--directory", type=Path, help="Directorio del proyecto (predeterminado: directorio actual)")
    p.add_argument("--no-banner", action="store_true", help="No mostrar el banner")
    p.add_argument("--update", action="store_true", help="Actualizar archivos de integración de KatalIArc existentes")
    p.add_argument("--language", choices=["es", "en"], help="Idioma de los artefactos iniciales")
    p.add_argument("--no-music", action="store_true", help="Silencia la melodía retro durante el inicio")
    p.add_argument("--rag-vector-store-id", help="ID of an existing OpenAI vector store for Toulmin retrieval")
    p.add_argument("--global", action="store_true", dest="global_scope", help="Instala skills e instrucciones en el directorio de usuario")
    subs.add_parser("validate", help="Valida JSON y trazabilidad entre artefactos")
    subs.add_parser("status", help="Muestra artefactos y prioridades pendientes")
    rag_parser = subs.add_parser("rag-test", help="Checks one read-only query against the configured ADR vector store")
    rag_parser.add_argument("--query", default="architecture decision records", help="Search text sent to the vector store")
    rag_parser.add_argument("--max-results", type=int, default=3, help="Maximum results to return (1–5)")
    doctor_parser = subs.add_parser("doctor", help="Diagnostica la instalación sin modificar archivos")
    doctor_parser.add_argument("--json", action="store_true", dest="as_json", help="Imprime resultados JSON sin color")
    doctor_parser.add_argument("--global", action="store_true", dest="global_scope", help="Diagnostica la instalación de usuario")
    update_parser = subs.add_parser("update", help="Actualiza recursos locales gestionados de forma segura")
    update_parser.add_argument("--dry-run", action="store_true", help="Muestra cambios sin escribir")
    update_parser.add_argument("--yes", "-y", action="store_true", help="Aplica cambios sin interacción")
    update_parser.add_argument("--global", action="store_true", dest="global_scope", help="Actualiza la instalación de usuario")
    p = subs.add_parser("decide", help="Manage ADR review, approval, and indexing")
    actions = p.add_mutually_exclusive_group(required=True)
    actions.add_argument("--show", metavar="ADR_ID", help="Show a persisted ADR and its lifecycle/indexing state")
    actions.add_argument("--accept", metavar="ADR_ID", help="Explicitly accept the current ADR version and queue asynchronous RAG indexing")
    actions.add_argument("--reject", metavar="ADR_ID", help="Reject an ADR proposal")
    actions.add_argument("--request-changes", metavar="ADR_ID", help="Move a proposal to UNDER_REVIEW with feedback")
    actions.add_argument("--history", metavar="ADR_ID", help="Show ADR lifecycle and approval history")
    actions.add_argument("--retry-index", metavar="ADR_ID", help="Retry indexing an accepted ADR")
    p.add_argument("--approver", help="Approval actor recorded with acceptance")
    p.add_argument("--note", default="", help="Approval/rejection/revision note")
    p.add_argument("--supersedes", help="Accepted ADR ID replaced by the newly accepted ADR")
    for role, actions in ROLE_ACTIONS.items():
        action_summary = "; ".join(f"kataliarc {role} {action}" for action in actions)
        role_parser = subs.add_parser(role, help=f"Acciones: {action_summary}")
        role_actions = role_parser.add_subparsers(dest="role_action", required=True)
        for action in actions:
            action_parser = role_actions.add_parser(action, help=f"Invoca {role} para la fase {action}")
            if action == "design":
                action_parser.add_argument("--repo", type=Path, help="Target repository for read-only analysis (default: current directory)")
                action_parser.add_argument("--no-rag", action="store_true", help="Run Toulmin without searching the vector store")
    help_parser = subs.add_parser("help", help="Muestra los comandos disponibles")
    help_parser.add_argument("topic", nargs="?", help="Comando del que se quiere ver la ayuda detallada")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "help":
        if args.topic:
            subparsers = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
            if args.topic not in subparsers.choices:
                parser.error(f"comando desconocido para help: {args.topic}")
            subparsers.choices[args.topic].print_help()
        else:
            parser.print_help()
        return
    if args.index_adr_worker:
        if args.supersede_adr_worker:
            _supersede_remote(args.supersede_adr_worker)
        raise SystemExit(_index_accepted_adr(args.index_adr_worker))
    if args.command is None:
        build_parser().error("se requiere un comando (por ejemplo: init, validate, status)")
    if args.command == "init":
        interactive = args.agent is None and sys.stdin.isatty() and sys.stdout.isatty()
        if args.agent is None and not interactive:
            build_parser().error("en una terminal no interactiva indica --agent; usa --directory y --language si corresponde")
        result = init(args.agent or "codex", Path.home() if args.global_scope else args.directory, overwrite=args.update, interactive=interactive, no_banner=args.no_banner, no_music=args.no_music, confirm=interactive, language=args.language, global_scope=args.global_scope, rag_vector_store_id=args.rag_vector_store_id)
    else:
        if args.command == "validate":
            result = validate()
        elif args.command == "status":
            result = status()
        elif args.command == "rag-test":
            result = rag_test(args.query, args.max_results)
        elif args.command == "doctor":
            result = run_doctor(Path.home() if args.global_scope else Path.cwd(), as_json=args.as_json)
        elif args.command == "update":
            result = run_update(Path.home() if args.global_scope else Path.cwd(), dry_run=args.dry_run, yes=args.yes)
        elif args.command == "decide":
            result = decide_action(show=args.show, accept=args.accept, reject=args.reject, request_changes=args.request_changes, history=args.history, retry_index=args.retry_index, actor=args.approver, note=args.note, supersedes=args.supersedes)
        elif args.command in ROLE_ACTIONS:
            stage = args.role_action
            result = run_stage(stage, True, repository=getattr(args, "repo", None), rag_enabled=not getattr(args, "no_rag", False))
        else:
            result = 2
    raise SystemExit(result)


if __name__ == "__main__":
    main()
