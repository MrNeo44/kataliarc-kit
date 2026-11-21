"""Validate Walton's evidence and compute the disposition of each alternative."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator


RUBRIC_VERSION = "kataliarc-walton-unified-v2"
CRITERIA = ("C1", "C2", "C3", "C4", "C5", "C6")
DECISION_RULES = (
    ("NO_CUMPLE", "DESCARTAR", "R1"),
    ("INCIERTO", "POSPONER", "R2"),
    ("REQUIERE_AJUSTE", "MODIFICAR", "R3"),
    ("CUMPLE", "MANTENER", "R4"),
)
VALUES = tuple(value for value, _, _ in DECISION_RULES)


def decide_alternative(values: dict[str, str]) -> tuple[str, str]:
    """Return the action and rule after checking the six input judgments."""
    if not isinstance(values, dict) or values.keys() != set(CRITERIA):
        raise ValueError("An alternative must have exactly the criteria C1 through C6.")
    if any(value not in VALUES for value in values.values()):
        raise ValueError("Invalid criterion value.")
    return next((action, rule) for value, action, rule in DECISION_RULES if value in values.values())


@lru_cache(maxsize=2)
def _validator(name: str) -> Draft202012Validator:
    path = Path(__file__).resolve().parent / "resources" / "schemas" / f"{name}.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _schema_errors(name: str, value: dict) -> list[str]:
    return [
        f"{name}.json{'.' if error.json_path != '$' else ''}{error.json_path[2:]}: {error.message}"
        for error in sorted(_validator(name).iter_errors(value), key=lambda error: (error.json_path, error.message))
    ]


def validate_rubric(rubric: dict) -> list[str]:
    errors = _schema_errors("walton-rubric", rubric)
    if errors:
        return errors
    if tuple(item["id"] for item in rubric["criteria"]) != CRITERIA:
        errors.append("walton-rubric.json: criteria must be C1 through C6 in order")
    declared = tuple((item["value"], item["action"], item["rule"]) for item in rubric["decision_rules"])
    if declared != DECISION_RULES or set(rubric["values"]) != set(VALUES):
        errors.append("walton-rubric.json: values and decision_rules must match the deterministic rules")
    return errors


def _scenario_scope(scenarios: dict, utility: dict) -> set[str]:
    tree_ids = {
        sid for branch in utility.get("quality_attributes", []) if isinstance(branch, dict)
        for sid in branch.get("scenario_ids", []) if isinstance(sid, str)
    }
    prioritized = {sid for sid, item in scenarios.items() if item.get("priority") in ("A", "M", "B") or item.get("mandatory") is True}
    return (tree_ids | prioritized) or set(scenarios)


def _by_id(rows: list) -> dict:
    return {row["id"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str) and row["id"]}


def _evaluate(evaluation: dict, context: dict, tactics: dict, utility: dict) -> tuple[list[str], list[dict]]:
    if isinstance(evaluation, dict) and evaluation.get("rubric_version") != RUBRIC_VERSION:
        return [f"evaluation.json: use {RUBRIC_VERSION}; rerun kataliarc walton evaluate for previous evaluations"], []
    errors = _schema_errors("evaluation", evaluation)
    if errors:
        return errors, []
    if any(not isinstance(source, dict) for source in (context, tactics, utility)):
        return ["Walton requires object artifacts for context, tactics, and the utility tree"], []
    for source, key in (
        (tactics, "alternatives"), (tactics, "tactics"),
        (context, "quality_scenarios"), (context, "constraints"),
        (utility, "quality_attributes"),
    ):
        if not isinstance(source.get(key, []), list):
            return [f"Walton requires {key} to be an array"], []
    for branch in utility.get("quality_attributes", []):
        if not isinstance(branch, dict) or not isinstance(branch.get("scenario_ids", []), list):
            return ["Walton requires scenario_ids arrays in utility-tree branches"], []

    alternatives = _by_id(tactics.get("alternatives", []))
    scenarios = _by_id(context.get("quality_scenarios", []))
    tactic_ids = _by_id(tactics.get("tactics", []))
    mandatory_constraints = {
        constraint_id for constraint_id, constraint in _by_id(context.get("constraints", [])).items()
        if constraint.get("mandatory") is True
    }
    scope = _scenario_scope(scenarios, utility)
    if alternatives and not scope:
        errors.append("evaluation.json: at least one quality scenario is required for each alternative")
    if len(alternatives) != len(tactics.get("alternatives", [])):
        errors.append("tactics.json: alternatives require distinct, nonempty IDs")
    if scope - scenarios.keys():
        errors.append("evaluation.json: the utility tree references unknown scenarios")

    pairs = set()
    grouped: dict[str, list[dict]] = {alt: [] for alt in alternatives}
    for row in evaluation["assessments"]:
        alternative, scenario = row["alternative_id"], row["scenario_id"]
        pair = alternative, scenario
        if pair in pairs:
            errors.append(f"evaluation.json: duplicate assessment {alternative}/{scenario}")
        pairs.add(pair)
        if alternative not in alternatives or scenario not in scenarios:
            errors.append(f"evaluation.json: unknown alternative or scenario in assessment {alternative}/{scenario}")
            continue
        for criterion, judgment in row["criteria"].items():
            if judgment["value"] != "NO_CUMPLE":
                continue
            reference = judgment["impediment_ref"]
            if reference.get("scenario_id") != scenario and reference.get("constraint_id") not in mandatory_constraints:
                errors.append(
                    f"evaluation.json: {alternative}/{scenario}/{criterion} impediment_ref "
                    "must reference the assessed scenario or a recorded mandatory constraint"
                )
        members = set(row["tactic_ids"])
        declared = alternatives[alternative].get("tactic_ids")
        if not members.issubset(tactic_ids):
            errors.append(f"evaluation.json: {alternative}/{scenario} references unknown tactics")
        if declared is not None and (
            not isinstance(declared, list)
            or not all(isinstance(tactic, str) for tactic in declared)
            or set(declared) != members
        ):
            errors.append(f"evaluation.json: {alternative}/{scenario} must assess the full set of tactics in the alternative")
        if grouped[alternative] and members != set(grouped[alternative][0]["tactic_ids"]):
            errors.append(f"evaluation.json: inconsistent tactic membership for {alternative}")
        grouped[alternative].append(row)

    expected = {(alternative, scenario) for alternative in alternatives for scenario in scope}
    for field, scenario_key, alternative_key in (
        ("risks", "scenario_ids", "decision_id"),
        ("no_risks", "scenario_ids", "decision_id"),
        ("sensitivity_points", "scenario_id", "alternative_id"),
        ("tradeoffs", "affected_scenario_ids", "decision_id"),
    ):
        for finding in evaluation.get(field, []):
            alternative = finding[alternative_key]
            if alternative not in alternatives:
                errors.append(f"evaluation.json: {field} references unknown alternative {alternative}")
            affected = [finding[scenario_key]] if scenario_key == "scenario_id" else finding[scenario_key]
            expected.update((alternative, scenario) for scenario in affected)
    missing = sorted(expected - pairs)
    if missing:
        errors.append("evaluation.json: missing alternative/scenario coverage: " + ", ".join(f"{a}/{s}" for a, s in missing))

    for request in evaluation["iteration_requests"]:
        if not set(request["target_alternative_ids"]).issubset(alternatives):
            errors.append("evaluation.json: iteration request references unknown alternatives")
        if not set(request["target_scenario_ids"]).issubset(scenarios):
            errors.append("evaluation.json: iteration request references unknown scenarios")
    if errors:
        return errors, []

    results = []
    for alternative, rows in sorted(grouped.items()):
        criteria = {}
        for criterion in CRITERIA:
            values = {row["criteria"][criterion]["value"] for row in rows}
            criteria[criterion] = next(value for value in VALUES if value in values)
        action, rule = decide_alternative(criteria)
        results.append({
            "alternative_id": alternative,
            "scenario_ids": sorted(row["scenario_id"] for row in rows),
            "tactic_ids": sorted(rows[0]["tactic_ids"]),
            "criteria": criteria,
            "action": action,
            "rule": rule,
        })
    return [], results


def validate_evaluation(evaluation: dict, context: dict, tactics: dict, utility_tree: dict) -> list[str]:
    """Check the saved artifact, including its derived results."""
    errors, derived = _evaluate(evaluation, context, tactics, utility_tree)
    if not errors and evaluation.get("alternative_results", []) != derived:
        errors.append("evaluation.json: alternative_results do not match the deterministic rules; run kataliarc walton evaluate --finalize")
    return errors


def finalize_evaluation(evaluation: dict, context: dict, tactics: dict, utility_tree: dict) -> dict:
    """Replace any supplied outcomes with the results of validated judgments."""
    draft = {key: value for key, value in evaluation.items() if key != "alternative_results"} if isinstance(evaluation, dict) else evaluation
    errors, results = _evaluate(draft, context, tactics, utility_tree)
    if errors:
        raise ValueError("\n".join(errors))
    return {**draft, "alternative_results": results}


def prepare_refinements(evaluation: dict) -> None:
    """Use the existing bounded iteration flow for actionable changes only."""
    modifiable = {row["alternative_id"] for row in evaluation["alternative_results"] if row["action"] == "MODIFICAR"}
    requests = evaluation["iteration_requests"]
    for request in requests:
        if request.get("status", "PENDING") == "PENDING" and not set(request["target_alternative_ids"]).issubset(modifiable):
            request["status"] = "UNRESOLVED"
    pending = {
        alternative for request in requests if request.get("status", "PENDING") == "PENDING"
        for alternative in request["target_alternative_ids"]
    }
    for alternative in sorted(modifiable - pending):
        adjustments = {
            f"{row['scenario_id']} {criterion}: {value['adjustment']}"
            for row in evaluation["assessments"] if row["alternative_id"] == alternative
            for criterion, value in row["criteria"].items() if value["value"] == "REQUIERE_AJUSTE"
        }
        requests.append({
            "request_type": "argument_revision",
            "reason": "R3 MODIFICAR",
            "target_alternative_ids": [alternative],
            "target_scenario_ids": sorted({
                row["scenario_id"] for row in evaluation["assessments"] if row["alternative_id"] == alternative
                and any(value["value"] == "REQUIERE_AJUSTE" for value in row["criteria"].values())
            }),
            "request_for_toulmin": "\n".join(sorted(adjustments)),
            "status": "PENDING",
        })
