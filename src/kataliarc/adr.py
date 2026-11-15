"""Persistent ADR proposals, explicit approvals, and local lifecycle history."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any


ADR_STATUSES = {"PROPOSED", "UNDER_REVIEW", "ACCEPTED", "REJECTED", "SUPERSEDED"}
INDEX_STATUSES = {"NOT_REQUESTED", "PENDING", "INDEXING", "INDEXED", "FAILED"}
REQUIRED_SECTIONS = {
    "architectural_problem", "business_context_and_objectives", "quality_scenarios", "constraints",
    "selected_tactics", "alternatives_considered", "recommended_decision", "toulmin_arguments",
    "qualitative_scenario_assessments", "evaluation_method", "risks_and_sensitivities", "tradeoffs",
    "walton_critical_questions", "objections_and_counterarguments", "evidence_and_references",
    "assumptions_and_uncertainties", "expected_consequences", "pending_verification",
    "evaluation_iterations", "unresolved_evaluation_requests",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _clean_id(value: str) -> str:
    value = value.strip().upper()
    if not re.fullmatch(r"ADR-[0-9]{3,}", value):
        raise ValueError("ADR ID must have the form ADR-001.")
    return value


def adr_path(root: Path, adr_id: str) -> Path:
    return root / "decisions" / f"{_clean_id(adr_id)}.json"


def markdown_path(root: Path, adr_id: str) -> Path:
    return root / "decisions" / f"{_clean_id(adr_id)}.md"


def load_adr(root: Path, adr_id: str) -> dict:
    adr_id = _clean_id(adr_id)
    path = adr_path(root, adr_id)
    value = _read(path, None)
    if not isinstance(value, dict) or value.get("adr_id") != adr_id.upper():
        raise ValueError(f"ADR not found or invalid: {adr_id}")
    return value


def list_adrs(root: Path) -> list[dict]:
    result = []
    for path in sorted((root / "decisions").glob("ADR-*.json")):
        value = _read(path, None)
        if isinstance(value, dict) and value.get("adr_id") and value.get("status") in ADR_STATUSES:
            result.append(value)
    return result


def _source(root: Path, name: str, default: Any) -> Any:
    return _read(root / name, default)


def _review_questions(review: dict) -> list:
    questions = review.get("critical_questions", review.get("questions", []))
    if not isinstance(questions, list):
        return []
    return questions


def compose_sections(root: Path, proposal: dict | None = None) -> dict:
    context = _source(root, "context.json", {})
    context_notes = root / "context.md"
    tactics = _source(root, "tactics.json", {})
    evaluation = _source(root, "evaluation.json", {})
    review = _source(root, "review.json", {})
    toulmin_input = _source(root, "toulmin-input.json", {})
    decision = _source(root, "decision.json", {})
    proposal = proposal if isinstance(proposal, dict) else {}
    scenarios = context.get("quality_scenarios", []) if isinstance(context, dict) else []
    utility = _source(root, "utility-tree.json", {})
    branches = utility.get("quality_attributes", []) if isinstance(utility, dict) else []
    branch_by_id = {}
    for branch in branches if isinstance(branches, list) else []:
        if isinstance(branch, dict):
            for scenario_id in branch.get("scenario_ids", []):
                branch_by_id.setdefault(scenario_id, branch.get("name"))
    scenario_records = []
    for scenario in scenarios if isinstance(scenarios, list) else []:
        if not isinstance(scenario, dict):
            continue
        scenario_records.append({**scenario, "utility_tree_attribute": branch_by_id.get(scenario.get("id"))})
    recommendation = proposal.get("recommended_decision") or decision.get("rationale") or decision.get("selected_alternative_id") or (evaluation.get("comparison", {}) or {}).get("recommendation")
    alternatives = tactics.get("alternatives", []) if isinstance(tactics, dict) else []
    selected_ids = {decision.get("selected_alternative_id")} if isinstance(decision, dict) else set()
    if isinstance(recommendation, dict):
        selected_ids.add(recommendation.get("alternative_id") or recommendation.get("selected_alternative_id"))
    discarded = [item for item in alternatives if isinstance(item, dict) and item.get("id") not in selected_ids] if any(selected_ids) else []
    historical_refs = proposal.get("historical_adr_refs", [])
    if not historical_refs and isinstance(toulmin_input, dict):
        rag = toulmin_input.get("rag", {})
        hits = rag.get("results", []) if isinstance(rag, dict) else []
        historical_refs = [
            {"adr_id": hit.get("attributes", {}).get("adr_id"), "adr_version": hit.get("attributes", {}).get("adr_version"), "source": hit.get("filename") or hit.get("file_id"), "transfer_status": "contextual claim; validate for this project"}
            for hit in hits if isinstance(hit, dict) and isinstance(hit.get("attributes"), dict)
            and hit["attributes"].get("origin") == "kataliarc"
            and hit["attributes"].get("decision_status") == "ACCEPTED"
        ]
    return {
        "architectural_problem": proposal.get("architectural_problem") or context.get("architectural_problem") or "Not explicitly recorded; clarify with stakeholders.",
        "business_context_and_objectives": {
            "stakeholder_context_notes": context_notes.read_text(encoding="utf-8").strip() if context_notes.is_file() else "",
            "architectural_context": context.get("architectural_context", {}),
            "business_goals": context.get("business_goals", []),
            "business_requirements": context.get("business_requirements", []),
            "references": context.get("references", []),
        },
        "quality_scenarios": scenario_records,
        "constraints": context.get("constraints", []),
        "selected_tactics": proposal.get("selected_tactics") or tactics.get("tactics", []),
        "alternatives_considered": {
            "all": alternatives,
            "discarded": discarded,
        },
        "recommended_decision": recommendation or "No recommendation was recorded; decision remains provisional.",
        "toulmin_arguments": tactics.get("scenario_arguments", []),
        "qualitative_scenario_assessments": evaluation.get("assessments", []),
        "evaluation_method": {
            "kind": "qualitative_nfr_grl_scenario_assessment",
            "rubric_version": evaluation.get("rubric_version", "nfr-grl-qualitative-v1"),
            "source": ".kataliarc/evaluation.json",
            "note": "This records the project's qualitative assessment; it is not proof of empirical compliance.",
        },
        "risks_and_sensitivities": proposal.get("risks_and_sensitivities") or {
            "risks": evaluation.get("risks", []) or decision.get("risks", []),
            "sensitivity_points": evaluation.get("sensitivity_points", []),
        },
        "tradeoffs": proposal.get("tradeoffs") or evaluation.get("tradeoffs", []) or decision.get("tradeoffs", []) or (evaluation.get("comparison", {}) or {}).get("tradeoffs", []),
        "walton_critical_questions": [
            *[question for assessment in evaluation.get("assessments", []) if isinstance(assessment, dict) for question in assessment.get("critical_question_assessments", [])],
            *_review_questions(review),
        ],
        "objections_and_counterarguments": review.get("objections", []) if isinstance(review, dict) else [],
        "evidence_and_references": {
            "tactic_catalog_refs": [ref for tactic in tactics.get("tactics", []) if isinstance(tactic, dict) for ref in tactic.get("source_refs", [])],
            "historical_adr_refs": historical_refs,
            "project_refs": context.get("references", []),
        },
        "assumptions_and_uncertainties": proposal.get("assumptions_and_uncertainties", decision.get("unresolved_questions", [])),
        "expected_consequences": proposal.get("expected_consequences", []),
        "pending_verification": proposal.get("pending_verification", decision.get("unresolved_questions", [])),
        "evaluation_iterations": evaluation.get("iteration_history", []),
        "unresolved_evaluation_requests": [request for request in evaluation.get("iteration_requests", []) if isinstance(request, dict) and request.get("status", "PENDING") in {"PENDING", "UNRESOLVED"}],
    }


def _render_value(value: Any) -> str:
    if value in (None, "", [], {}):
        return "Not recorded."
    if isinstance(value, str):
        return value
    return "```json\n" + json.dumps(value, ensure_ascii=False, indent=2) + "\n```"


def render_markdown(record: dict) -> str:
    version = record["current_version"]
    sections = version["sections"]
    heading_map = [
        ("architectural_problem", "Architectural problem"),
        ("business_context_and_objectives", "Business context and objectives"),
        ("quality_scenarios", "Quality scenarios and utility-tree grouping"),
        ("constraints", "Architectural constraints"),
        ("selected_tactics", "Selected tactics"),
        ("alternatives_considered", "Alternatives considered and discarded"),
        ("recommended_decision", "Recommended decision"),
        ("toulmin_arguments", "Toulmin arguments"),
        ("qualitative_scenario_assessments", "Qualitative NFR/GRL scenario assessment"),
        ("evaluation_method", "Evaluation method and rubric"),
        ("risks_and_sensitivities", "Risks and sensitivity points"),
        ("tradeoffs", "Trade-offs"),
        ("walton_critical_questions", "Walton critical questions"),
        ("objections_and_counterarguments", "Objections and counterarguments"),
        ("evidence_and_references", "Evidence and references"),
        ("assumptions_and_uncertainties", "Assumptions and uncertainties"),
        ("expected_consequences", "Expected consequences"),
        ("pending_verification", "Pending verification"),
        ("evaluation_iterations", "Evaluation and refinement history"),
        ("unresolved_evaluation_requests", "Unresolved requests for Toulmin"),
    ]
    approvals = [item for item in record.get("approval_history", []) if item.get("version") == version["version"]]
    approval = _render_value(approvals[-1]) if approvals else "No approval recorded for this version."
    lines = [f"# {record['adr_id']}: {version['title']}", "", f"- Status: **{record['status']}**", f"- Version: {version['version']}", f"- Proposed at: {version['created_at']}", f"- Approval: {approval}", ""]
    for key, heading in heading_map:
        lines.extend((f"## {heading}", "", _render_value(sections.get(key)), ""))
    lines.extend(("## Approval record", "", _render_value(record.get("approval_history", [])), "", "## Indexing", "", _render_value(record.get("indexing", {})), ""))
    return "\n".join(lines)


def _save(root: Path, record: dict) -> None:
    _write(adr_path(root, record["adr_id"]), record)
    markdown_path(root, record["adr_id"]).write_text(render_markdown(record), encoding="utf-8")


def _event(record: dict, status: str, actor: str, note: str = "", **extra: Any) -> None:
    record.setdefault("history", []).append({"status": status, "at": utc_now(), "actor": actor, "note": note, **extra})
    record["status"] = status
    record["updated_at"] = utc_now()


def create_proposals(root: Path, proposals: list[dict] | None = None) -> list[dict]:
    """Create/update proposed ADR versions from traceable phase artifacts."""
    existing = list_adrs(root)
    review_path = root / "review.json"
    if not review_path.is_file():
        raise ValueError("Walton review.json is missing; no proposal was persisted.")
    try:
        review = json.loads(review_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise ValueError("Walton review.json is invalid; no proposal was persisted.") from None
    if not isinstance(review, dict) or not any(key in review for key in ("review_summary", "critical_questions", "questions", "decision_proposals")):
        raise ValueError("Walton review.json has no review summary, critical questions, or decision proposals.")
    if proposals is None:
        candidates = review.get("decision_proposals") if isinstance(review, dict) else None
        if isinstance(candidates, list) and candidates:
            proposals = candidates
        else:
            proposals = [{key: review[key] for key in ("title", "architectural_problem", "recommended_decision", "selected_tactics", "risks_and_sensitivities", "tradeoffs", "historical_adr_refs", "assumptions_and_uncertainties", "expected_consequences", "pending_verification") if isinstance(review, dict) and key in review}]
    pending = next((r for r in sorted(existing, key=lambda item: item.get("adr_id", ""), reverse=True) if r.get("status") == "UNDER_REVIEW"), None)
    created = []
    for index, proposal in enumerate(proposals, start=1):
        if pending and index == 1:
            record = pending
            version_number = max((v.get("version", 0) for v in record.get("versions", [])), default=0) + 1
            title = proposal.get("title") or record.get("current_version", {}).get("title", f"Architecture decision {record['adr_id']}")
            version = {"version": version_number, "created_at": utc_now(), "title": title, "sections": compose_sections(root, proposal), "source_artifacts": ["context.md", "context.json", "utility-tree.json", "tactics.json", "evaluation.json", "review.json", "decision.json", "toulmin-input.json"]}
            record.setdefault("versions", []).append(version)
            record["current_version"] = version
            _event(record, "PROPOSED", "walton", "Revision submitted for review", version=version_number)
            record["approval_history"] = []
            record["indexing"] = {"status": "NOT_REQUESTED", "attempts": [], "history": [], "remote_resources": []}
        else:
            number = max([int(r["adr_id"].split("-")[1]) for r in existing if re.fullmatch(r"ADR-[0-9]{3,}", r["adr_id"])] + [0]) + 1
            adr_id = f"ADR-{number:03d}"
            version = {"version": 1, "created_at": utc_now(), "title": proposal.get("title") or f"Architecture decision {adr_id}", "sections": compose_sections(root, proposal), "source_artifacts": ["context.md", "context.json", "utility-tree.json", "tactics.json", "evaluation.json", "review.json", "decision.json", "toulmin-input.json"]}
            config = _source(root, "config.json", {})
            record = {"adr_id": adr_id, "project_id": config.get("project_id", "unknown"), "origin": "kataliarc", "status": "PROPOSED", "created_at": version["created_at"], "updated_at": version["created_at"], "current_version": version, "versions": [version], "history": [{"status": "PROPOSED", "at": version["created_at"], "actor": "walton", "note": "ADR proposal generated after critical review."}], "approval_history": [], "indexing": {"status": "NOT_REQUESTED", "attempts": [], "history": [], "remote_resources": []}}
        _save(root, record)
        created.append(record)
        existing.append(record)
        if pending:
            pending = None
    return created


def transition(root: Path, adr_id: str, action: str, *, actor: str = "local-user", note: str = "", supersedes: str | None = None) -> dict:
    record = load_adr(root, adr_id)
    status = record["status"]
    if action == "accept":
        if status not in {"PROPOSED", "UNDER_REVIEW"}:
            raise ValueError(f"Cannot accept an ADR in {status} state.")
        version = record["current_version"]["version"]
        accepted_at = utc_now()
        record["approval_history"].append({"action": "ACCEPTED", "actor": actor, "version": version, "at": accepted_at, "note": note})
        _event(record, "ACCEPTED", actor, note, version=version)
        record["indexing"] = {"status": "PENDING", "attempts": record.get("indexing", {}).get("attempts", []), "history": record.get("indexing", {}).get("history", []) + [{"status": "PENDING", "at": accepted_at, "detail": "Explicit user approval requested indexing."}], "remote_resources": record.get("indexing", {}).get("remote_resources", []), "accepted_at": accepted_at}
        if supersedes:
            old = load_adr(root, supersedes)
            if old["status"] != "ACCEPTED":
                raise ValueError("Only an accepted ADR can be superseded.")
            _event(old, "SUPERSEDED", actor, f"Superseded by {record['adr_id']}.", superseded_by=record["adr_id"])
            _save(root, old)
            record["supersedes"] = old["adr_id"]
    elif action == "reject":
        if status not in {"PROPOSED", "UNDER_REVIEW"}:
            raise ValueError(f"Cannot reject an ADR in {status} state.")
        record["approval_history"].append({"action": "REJECTED", "actor": actor, "version": record["current_version"]["version"], "at": utc_now(), "note": note})
        _event(record, "REJECTED", actor, note, version=record["current_version"]["version"])
    elif action == "request-changes":
        if status not in {"PROPOSED", "UNDER_REVIEW"}:
            raise ValueError(f"Cannot request changes for an ADR in {status} state.")
        _event(record, "UNDER_REVIEW", actor, note, version=record["current_version"]["version"])
    elif action == "supersede":
        if status != "ACCEPTED":
            raise ValueError("Only an accepted ADR can be superseded.")
        _event(record, "SUPERSEDED", actor, note)
    else:
        raise ValueError(f"Unsupported ADR action: {action}")
    _save(root, record)
    return record


def update_indexing(root: Path, adr_id: str, status: str, *, detail: str = "", remote: dict | None = None, file_id: str | None = None) -> dict:
    if status not in INDEX_STATUSES:
        raise ValueError(f"Invalid indexing status: {status}")
    record = load_adr(root, adr_id)
    if record.get("status") not in {"ACCEPTED", "SUPERSEDED"}:
        raise ValueError("Only accepted ADRs can have an indexing operation.")
    indexing = record.setdefault("indexing", {})
    indexing["status"] = status
    indexing["updated_at"] = utc_now()
    indexing.setdefault("history", []).append({"status": status, "at": indexing["updated_at"], "detail": detail})
    if file_id:
        indexing["file_id"] = file_id
    if detail:
        indexing["last_error"] = detail if status == "FAILED" else None
    if remote:
        indexing.setdefault("remote_resources", [])
        stable = remote.get("index_key")
        if not any(item.get("index_key") == stable for item in indexing["remote_resources"]):
            indexing["remote_resources"].append(remote)
    if status in {"INDEXING", "FAILED"}:
        indexing.setdefault("attempts", []).append({"status": status, "at": utc_now(), "detail": detail})
    _save(root, record)
    return record


def validate_record(record: dict) -> None:
    required = {"adr_id", "project_id", "origin", "status", "current_version", "versions", "history", "approval_history", "indexing"}
    missing = required - record.keys()
    if missing:
        raise ValueError("ADR JSON missing fields: " + ", ".join(sorted(missing)))
    if record["status"] not in ADR_STATUSES:
        raise ValueError("Invalid ADR lifecycle status.")
    if record["origin"] != "kataliarc" or not isinstance(record["project_id"], str) or not record["project_id"]:
        raise ValueError("ADR origin or project_id is invalid.")
    if not isinstance(record["current_version"], dict) or not isinstance(record["current_version"].get("sections"), dict):
        raise ValueError("ADR current_version must contain structured sections.")
    current = record["current_version"]
    if not isinstance(current.get("version"), int) or not isinstance(current.get("title"), str) or not isinstance(current.get("created_at"), str):
        raise ValueError("ADR current_version is missing version metadata.")
    missing_sections = REQUIRED_SECTIONS - record["current_version"]["sections"].keys()
    if missing_sections:
        raise ValueError("ADR sections missing: " + ", ".join(sorted(missing_sections)))
    if record["indexing"].get("status") not in INDEX_STATUSES or not isinstance(record["indexing"].get("history", []), list):
        raise ValueError("Invalid ADR indexing status.")
    if record["status"] in {"ACCEPTED", "SUPERSEDED"} and not any(
        event.get("action") == "ACCEPTED" and event.get("version") == record["current_version"].get("version")
        for event in record.get("approval_history", [])
    ):
        raise ValueError("Accepted ADR version has no matching explicit approval record.")


def approval_history(root: Path, adr_id: str) -> list[dict]:
    return load_adr(root, adr_id).get("history", [])


def index_document_text(record: dict) -> str:
    """Build a retrieval projection while retaining the complete local ADR as source of truth."""
    version = record["current_version"]
    sections = version["sections"]
    return render_markdown(record)


def metadata_for(record: dict, project_id: str) -> dict:
    version = record["current_version"]
    sections = version["sections"]
    scenario_ids = [str(item.get("id")) for item in sections.get("quality_scenarios", []) if isinstance(item, dict) and item.get("id")]
    tactic_ids = [str(item.get("id")) for item in sections.get("selected_tactics", []) if isinstance(item, dict) and item.get("id")]
    evaluation = sections.get("evaluation_method", {})
    metadata = {
        "adr_id": record["adr_id"],
        "adr_version": version["version"],
        "project_id": project_id,
        "source_type": "kataliarc_accepted_adr",
        "decision_status": record["status"],
        "accepted_at": record.get("indexing", {}).get("accepted_at", ""),
        "quality_scenario_ids": json.dumps(scenario_ids, ensure_ascii=False, separators=(",", ":")),
        "tactic_ids": json.dumps(tactic_ids, ensure_ascii=False, separators=(",", ":")),
        "rubric_version": evaluation.get("rubric_version", "nfr-grl-qualitative-v1"),
        "origin": "kataliarc",
        "index_key": index_key(project_id, record["adr_id"], version["version"]),
    }
    for key, value in metadata.items():
        if len(key) > 64 or len(str(value)) > 512:
            raise ValueError(f"RAG metadata field exceeds provider limit: {key}")
    return metadata


def index_key(project_id: str, adr_id: str, version: int) -> str:
    import hashlib
    payload = f"{project_id}\0{adr_id}\0{version}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
