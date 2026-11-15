"""Deterministic validation for Walton's qualitative scenario evaluation."""
from __future__ import annotations

from typing import Any


RUBRIC_VERSION = "kataliarc-quality-contribution-v1"
DIRECTIONS = {"POSITIVE", "NEGATIVE", "NEUTRAL", "UNKNOWN"}
SUFFICIENCY = {"SUFFICIENT", "INSUFFICIENT", "UNKNOWN"}
LABELS = {
    "MAKE (++)", "HELP (+)", "SomePositive", "HURT (-)", "BREAK (--)",
    "SomeNegative", "UNKNOWN (?)", "NEUTRAL (0)",
}
COMPLIANCE = {
    "VERIFIED_SATISFIED", "VERIFIED_UNSATISFIED", "PREDICTED_UNDER_ASSUMPTIONS", "UNVERIFIED",
    # Read compatibility for already generated artifacts.
    "verificado", "provisional", "incumplido", "desconocido",
}


def classify_contribution(direction: str, sufficiency: str, *, neutral_justified: bool = False) -> str:
    """Map explicit direction and sufficiency to the KatalIArc contribution label."""
    direction = direction.upper()
    sufficiency = sufficiency.upper()
    if direction not in DIRECTIONS:
        raise ValueError(f"Invalid contribution direction: {direction}")
    if sufficiency not in SUFFICIENCY:
        raise ValueError(f"Invalid contribution sufficiency: {sufficiency}")
    if direction == "UNKNOWN":
        return "UNKNOWN (?)"
    if direction == "NEUTRAL":
        if sufficiency != "UNKNOWN":
            raise ValueError("NEUTRAL uses UNKNOWN sufficiency; no objective is claimed as met or prevented.")
        if not neutral_justified:
            raise ValueError("NEUTRAL requires an explicit justification that no material effect is expected.")
        return "NEUTRAL (0)"
    if direction == "POSITIVE":
        return {"SUFFICIENT": "MAKE (++)", "INSUFFICIENT": "HELP (+)", "UNKNOWN": "SomePositive"}[sufficiency]
    return {"SUFFICIENT": "BREAK (--)", "INSUFFICIENT": "HURT (-)", "UNKNOWN": "SomeNegative"}[sufficiency]


def _scenario_scope(context: dict) -> list[str]:
    scenarios = context.get("quality_scenarios", [])
    all_ids = [str(item["id"]) for item in scenarios if isinstance(item, dict) and item.get("id")]
    tree_path = context.get("_utility_tree")
    if not isinstance(tree_path, dict):
        return all_ids
    referenced = {
        str(sid)
        for branch in tree_path.get("quality_attributes", []) if isinstance(branch, dict)
        for sid in branch.get("scenario_ids", [])
    }
    return [sid for sid in all_ids if sid in referenced] or all_ids


def _validate_object_list(evaluation: dict, key: str, fields: set[str], errors: list[str]) -> None:
    values = evaluation.get(key, [])
    if not isinstance(values, list):
        errors.append(f"evaluation.json: {key} must be an array")
        return
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            errors.append(f"evaluation.json: {key}[{index}] must be an object")
            continue
        missing = fields - value.keys()
        if missing:
            errors.append(f"evaluation.json: {key}[{index}] missing {', '.join(sorted(missing))}")


def validate_rubric(rubric: dict) -> list[str]:
    """Ensure the declarative rubric agrees with the deterministic classifier."""
    errors: list[str] = []
    if not isinstance(rubric, dict) or rubric.get("id") != RUBRIC_VERSION:
        return [f"walton-rubric.json: id must be {RUBRIC_VERSION}"]
    rules = rubric.get("contribution_rules")
    if not isinstance(rules, list):
        return ["walton-rubric.json: contribution_rules must be an array"]
    declared = {(row.get("direction"), row.get("sufficiency")): row.get("label") for row in rules if isinstance(row, dict)}
    expected = {
        (direction, sufficiency): classify_contribution(direction, sufficiency, neutral_justified=direction == "NEUTRAL")
        for direction in DIRECTIONS for sufficiency in SUFFICIENCY
        if not (direction == "NEUTRAL" and sufficiency != "UNKNOWN")
    }
    if declared != expected:
        errors.append("walton-rubric.json: contribution_rules do not match deterministic classification rules")
    if set(rubric.get("compliance_statuses", [])) != {"VERIFIED_SATISFIED", "VERIFIED_UNSATISFIED", "PREDICTED_UNDER_ASSUMPTIONS", "UNVERIFIED"}:
        errors.append("walton-rubric.json: compliance_statuses are invalid")
    return errors


def validate_evaluation(evaluation: dict, context: dict, tactics: dict, utility_tree: dict, *, rubric_version: str = RUBRIC_VERSION) -> list[str]:
    """Check coverage, references, rubric consistency, and traceable ATAM findings.

    This validates structural consistency only; it does not establish that a causal
    premise is technically true or that a measure has been empirically satisfied.
    """
    errors: list[str] = []
    if not isinstance(evaluation, dict):
        return ["evaluation.json must be an object"]
    if evaluation.get("rubric_version") != rubric_version:
        errors.append(f"evaluation.json: rubric_version must be {rubric_version}")
    assessments = evaluation.get("assessments")
    alternatives = tactics.get("alternatives", []) if isinstance(tactics, dict) else []
    alternative_ids = [str(item["id"]) for item in alternatives if isinstance(item, dict) and item.get("id")]
    tactic_ids = {str(item["id"]) for item in tactics.get("tactics", []) if isinstance(item, dict) and item.get("id")} if isinstance(tactics, dict) else set()
    ids = [str(item["id"]) for item in context.get("quality_scenarios", []) if isinstance(item, dict) and item.get("id")]
    relevant = set(_scenario_scope({**context, "_utility_tree": utility_tree}))
    scenario_ids = [sid for sid in ids if sid in relevant]
    if not isinstance(assessments, list):
        return ["evaluation.json: assessments must be an array"]
    seen: set[tuple[str, str]] = set()
    required_causal = {"claim", "mechanism", "evidence", "assumptions", "applicability_conditions", "expected_effect", "sufficiency_rationale", "counterarguments", "conclusion"}
    for index, item in enumerate(assessments):
        label = f"evaluation.json: assessments[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        alternative_id, scenario_id = item.get("alternative_id"), item.get("scenario_id")
        if alternative_id not in alternative_ids:
            errors.append(f"{label}: unknown alternative_id {alternative_id}")
        if scenario_id not in ids:
            errors.append(f"{label}: unknown scenario_id {scenario_id}")
        pair = (str(alternative_id), str(scenario_id))
        if pair in seen:
            errors.append(f"{label}: duplicate alternative/scenario assessment {pair}")
        seen.add(pair)
        for field in ("contribution_direction", "sufficiency", "contribution_label", "compliance_status", "causal_justification", "rubric_version"):
            if field not in item:
                errors.append(f"{label}: missing {field}")
        if item.get("contribution_direction") not in DIRECTIONS:
            errors.append(f"{label}: invalid contribution_direction")
        if item.get("sufficiency") not in SUFFICIENCY:
            errors.append(f"{label}: invalid sufficiency")
        if item.get("compliance_status") not in COMPLIANCE:
            errors.append(f"{label}: invalid compliance_status")
        if item.get("evidence_status") not in {"documentada", "inferencia/hipótesis", "desconocida"}:
            errors.append(f"{label}: invalid evidence_status")
        legacy_direction = {"POSITIVE": "favorable", "NEGATIVE": "desfavorable", "NEUTRAL": "condicionado", "UNKNOWN": "indeterminado"}.get(item.get("contribution_direction"))
        if legacy_direction and item.get("direction") != legacy_direction:
            errors.append(f"{label}: legacy direction must match contribution_direction ({legacy_direction})")
        causal = item.get("causal_justification")
        if not isinstance(causal, dict):
            errors.append(f"{label}: causal_justification must be an object")
        else:
            for field in required_causal:
                if field not in causal:
                    errors.append(f"{label}: causal_justification missing {field}")
            for field in ("evidence", "assumptions", "applicability_conditions", "counterarguments"):
                if field in causal and not isinstance(causal[field], list):
                    errors.append(f"{label}: causal_justification.{field} must be an array")
            for field in ("claim", "mechanism", "expected_effect", "sufficiency_rationale", "conclusion"):
                if field in causal and not isinstance(causal[field], str):
                    errors.append(f"{label}: causal_justification.{field} must be a string")
                elif field in causal and not causal[field].strip():
                    errors.append(f"{label}: causal_justification.{field} must not be empty")
        if item.get("rubric_version") != rubric_version:
            errors.append(f"{label}: rubric_version must be {rubric_version}")
        if item.get("contribution_direction") in DIRECTIONS and item.get("sufficiency") in SUFFICIENCY:
            try:
                derived = classify_contribution(
                    item["contribution_direction"], item["sufficiency"],
                    neutral_justified=bool(item.get("neutral_justified")),
                )
                if item.get("contribution_label") != derived:
                    errors.append(f"{label}: contribution_label {item.get('contribution_label')} conflicts with deterministic classification {derived}")
            except ValueError as exc:
                errors.append(f"{label}: {exc}")
        if item.get("compliance_status") in {"VERIFIED_SATISFIED", "VERIFIED_UNSATISFIED", "verificado", "incumplido"}:
            if not isinstance(causal, dict) or not causal.get("evidence"):
                errors.append(f"{label}: verified compliance requires explicit evidence references")
        for field in ("tactic_ids", "assumptions", "objections"):
            if field not in item or not isinstance(item[field], list):
                errors.append(f"{label}: {field} must be an array")
        if isinstance(item.get("tactic_ids"), list) and tactic_ids and not set(item["tactic_ids"]).issubset(tactic_ids):
            errors.append(f"{label}: tactic_ids contains an unknown tactic")
        questions = item.get("critical_question_assessments", [])
        if not isinstance(questions, list):
            errors.append(f"{label}: critical_question_assessments must be an array")
        else:
            for qindex, question in enumerate(questions):
                required = {"scheme", "question", "claim_ref", "answer", "result", "evidence_refs", "objection"}
                if not isinstance(question, dict) or required - question.keys():
                    errors.append(f"{label}: critical_question_assessments[{qindex}] is incomplete")
                elif question.get("scheme") not in {"practical_reasoning", "causal_argument", "analogy", "expert_opinion", "consequences"} or question.get("result") not in {"supported", "challenged", "unresolved"}:
                    errors.append(f"{label}: critical_question_assessments[{qindex}] has an invalid scheme or result")

    expected = {(alternative, scenario) for alternative in alternative_ids for scenario in scenario_ids}
    missing = sorted(expected - seen)
    if missing:
        errors.append("evaluation.json: missing alternative/scenario coverage: " + ", ".join(f"{a}/{s}" for a, s in missing))
    _validate_object_list(evaluation, "risks", {"id", "decision_id", "scenario_ids", "causal_mechanism", "consequence", "evidence", "status", "mitigation"}, errors)
    _validate_object_list(evaluation, "sensitivity_points", {"id", "property", "scenario_id", "response_measure", "causal_mechanism", "variation_effect", "status", "evidence"}, errors)
    _validate_object_list(evaluation, "tradeoffs", {"id", "decision_id", "property", "affected_scenario_ids", "positive_effects", "negative_effects", "shared_mechanism", "business_priorities", "assumptions", "evidence", "mitigations"}, errors)
    _validate_object_list(evaluation, "iteration_history", {"iteration", "action", "observation", "source_artifacts", "outcome"}, errors)
    known_scenarios = set(ids)
    known_alternatives = set(alternative_ids)
    for key, refs in (("risks", "scenario_ids"), ("sensitivity_points", "scenario_id"), ("tradeoffs", "affected_scenario_ids")):
        values = evaluation.get(key, [])
        if not isinstance(values, list):
            continue
        for index, value in enumerate(values):
            if not isinstance(value, dict):
                continue
            targets = value.get(refs, [])
            targets = [targets] if isinstance(targets, str) else targets
            if isinstance(targets, list):
                for target in targets:
                    if target not in known_scenarios:
                        errors.append(f"evaluation.json: {key}[{index}] references unknown scenario {target}")
            if key == "risks" and value.get("status") not in {"CONFIRMED_CONDITION", "HYPOTHETICAL", "CANDIDATE"}:
                errors.append(f"evaluation.json: risks[{index}] has invalid status")
            if key == "sensitivity_points" and value.get("status") not in {"SUPPORTED", "CANDIDATE"}:
                errors.append(f"evaluation.json: sensitivity_points[{index}] has invalid status")
            if key == "tradeoffs" and (not isinstance(value.get("affected_scenario_ids"), list) or len(set(value["affected_scenario_ids"])) < 2):
                errors.append(f"evaluation.json: tradeoffs[{index}] must affect at least two distinct scenarios")
    requests = evaluation.get("iteration_requests", [])
    if not isinstance(requests, list):
        errors.append("evaluation.json: iteration_requests must be an array")
    else:
        for index, request in enumerate(requests):
            fields = {"request_type", "reason", "target_scenario_ids", "target_alternative_ids", "request_for_toulmin"}
            if not isinstance(request, dict) or fields - request.keys():
                errors.append(f"evaluation.json: iteration_requests[{index}] is incomplete")
            elif request.get("request_type") not in {"new_tactic", "new_combination", "evidence", "argument_revision", "reevaluation"}:
                errors.append(f"evaluation.json: iteration_requests[{index}] has invalid request_type")
            else:
                if not isinstance(request.get("target_scenario_ids"), list) or not set(request["target_scenario_ids"]).issubset(known_scenarios):
                    errors.append(f"evaluation.json: iteration_requests[{index}] has invalid target_scenario_ids")
                if not isinstance(request.get("target_alternative_ids"), list) or not set(request["target_alternative_ids"]).issubset(known_alternatives):
                    errors.append(f"evaluation.json: iteration_requests[{index}] has invalid target_alternative_ids")
    return errors
