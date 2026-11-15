import json
from pathlib import Path

import pytest

from kataliarc import cli
from kataliarc.evaluation import RUBRIC_VERSION, classify_contribution, validate_evaluation, validate_rubric


@pytest.mark.parametrize(("direction", "sufficiency", "label"), [
    ("POSITIVE", "SUFFICIENT", "MAKE (++)"), ("POSITIVE", "INSUFFICIENT", "HELP (+)"),
    ("POSITIVE", "UNKNOWN", "SomePositive"), ("NEGATIVE", "INSUFFICIENT", "HURT (-)"),
    ("NEGATIVE", "SUFFICIENT", "BREAK (--)"), ("NEGATIVE", "UNKNOWN", "SomeNegative"),
    ("UNKNOWN", "UNKNOWN", "UNKNOWN (?)"),
])
def test_deterministic_contribution_labels(direction, sufficiency, label):
    assert classify_contribution(direction, sufficiency) == label


def test_neutral_requires_unknown_sufficiency_and_justification():
    with pytest.raises(ValueError):
        classify_contribution("NEUTRAL", "UNKNOWN")
    assert classify_contribution("NEUTRAL", "UNKNOWN", neutral_justified=True) == "NEUTRAL (0)"


def _assessment(alt, scenario, *, direction="POSITIVE", sufficiency="INSUFFICIENT", label="HELP (+)", compliance="UNVERIFIED", evidence=None):
    return {
        "alternative_id": alt, "scenario_id": scenario, "tactic_ids": ["T1"], "design_decision": "Use a bounded cache",
        "direction": {"POSITIVE": "favorable", "NEGATIVE": "desfavorable", "NEUTRAL": "condicionado", "UNKNOWN": "indeterminado"}[direction],
        "rationale": "The cache reduces repeated storage reads under the stated workload.",
        "contribution_direction": direction, "sufficiency": sufficiency, "contribution_label": label,
        "neutral_justified": direction == "NEUTRAL", "evidence_status": "documentada" if evidence else "inferencia/hipótesis",
        "compliance_status": compliance,
        "causal_justification": {"claim": "Caching reduces repeated reads.", "mechanism": "Repeated reads use in-memory data.", "evidence": evidence or [], "assumptions": ["Working set fits memory"], "applicability_conditions": ["Cache is enabled"], "expected_effect": "Lower read latency", "sufficiency_rationale": "The target still depends on workload and cache hit ratio.", "counterarguments": ["Cache misses still reach storage"], "conclusion": "Positive but insufficient contribution."},
        "assumptions": ["Working set fits memory"], "objections": [], "critical_question_assessments": [], "rubric_version": RUBRIC_VERSION,
    }


def _evaluation():
    context = {"quality_scenarios": [{"id": "QS1", "quality_attribute": "performance"}, {"id": "QS2", "quality_attribute": "availability"}]}
    tactics = {"alternatives": [{"id": "A1"}, {"id": "A2"}]}
    utility = {"quality_attributes": [{"name": "performance", "scenario_ids": ["QS1"]}, {"name": "availability", "scenario_ids": ["QS2"]}]}
    assessments = [_assessment(alt, scenario) for alt in ("A1", "A2") for scenario in ("QS1", "QS2")]
    evaluation = {"rubric_version": RUBRIC_VERSION, "assessments": assessments, "risks": [], "sensitivity_points": [], "tradeoffs": [], "iteration": 0, "iteration_requests": [], "iteration_history": []}
    return evaluation, context, tactics, utility


def test_complete_pairwise_coverage_and_label_contract():
    evaluation, context, tactics, utility = _evaluation()
    assert validate_evaluation(evaluation, context, tactics, utility) == []
    evaluation["assessments"].pop()
    assert any("missing alternative/scenario coverage" in error for error in validate_evaluation(evaluation, context, tactics, utility))


def test_direction_sufficiency_mapping_is_enforced():
    evaluation, context, tactics, utility = _evaluation()
    evaluation["assessments"][0]["contribution_label"] = "MAKE (++)"
    assert any("conflicts with deterministic classification" in error for error in validate_evaluation(evaluation, context, tactics, utility))


def test_contribution_is_separate_from_empirical_compliance():
    evaluation, context, tactics, utility = _evaluation()
    assessment = evaluation["assessments"][0]
    assert assessment["contribution_label"] == "HELP (+)"
    assert assessment["compliance_status"] == "UNVERIFIED"
    assessment["compliance_status"] = "VERIFIED_SATISFIED"
    assert any("verified compliance requires explicit evidence" in error for error in validate_evaluation(evaluation, context, tactics, utility))


def test_causal_justification_and_rubric_are_checked():
    evaluation, context, tactics, utility = _evaluation()
    evaluation["assessments"][0]["causal_justification"]["mechanism"] = ""
    assert any("causal_justification.mechanism must not be empty" in error for error in validate_evaluation(evaluation, context, tactics, utility))
    rubric = json.loads((Path(__file__).parents[1] / "src/kataliarc/resources/metamodel/walton-rubric.json").read_text())
    assert validate_rubric(rubric) == []


def test_risk_sensitivity_tradeoff_findings_need_traceable_fields():
    evaluation, context, tactics, utility = _evaluation()
    evaluation["risks"] = [{"id": "R1", "decision_id": "A1", "scenario_ids": ["QS1"], "causal_mechanism": "Cache stampede", "consequence": "Latency spike", "evidence": [], "status": "HYPOTHETICAL", "mitigation": "Jitter"}]
    evaluation["sensitivity_points"] = [{"id": "S1", "property": "TTL", "scenario_id": "QS1", "response_measure": {"metric": "p95", "operator": "<=", "value": 300, "unit": "ms"}, "causal_mechanism": "Eviction changes hit rate", "variation_effect": "Higher TTL may improve hit ratio", "status": "CANDIDATE", "evidence": []}]
    evaluation["tradeoffs"] = [{"id": "TO1", "decision_id": "A1", "property": "cache consistency", "affected_scenario_ids": ["QS1", "QS2"], "positive_effects": ["Lower latency"], "negative_effects": ["Stale reads"], "shared_mechanism": "Cache invalidation lag", "business_priorities": ["Performance"], "assumptions": [], "evidence": [], "mitigations": ["Short TTL"]}]
    assert validate_evaluation(evaluation, context, tactics, utility) == []
    evaluation["tradeoffs"][0]["affected_scenario_ids"] = ["missing"]
    assert any("references unknown scenario" in error for error in validate_evaluation(evaluation, context, tactics, utility))


def test_neutral_requires_explanation_and_unjustified_neutral_fails():
    evaluation, context, tactics, utility = _evaluation()
    item = evaluation["assessments"][0]
    item.update({"direction": "condicionado", "contribution_direction": "NEUTRAL", "sufficiency": "UNKNOWN", "contribution_label": "NEUTRAL (0)", "neutral_justified": False})
    assert any("explicit justification" in error for error in validate_evaluation(evaluation, context, tactics, utility))


def test_walton_question_schema_is_explicit():
    evaluation, context, tactics, utility = _evaluation()
    evaluation["assessments"][0]["critical_question_assessments"] = [{"scheme": "causal_argument", "question": "Is the relation supported?", "claim_ref": "A1/QS1", "answer": "Not by a measured test.", "result": "unresolved", "evidence_refs": [], "objection": "No benchmark"}]
    assert validate_evaluation(evaluation, context, tactics, utility) == []
    evaluation["assessments"][0]["critical_question_assessments"][0]["scheme"] = "generic"
    assert any("invalid scheme" in error for error in validate_evaluation(evaluation, context, tactics, utility))


def test_iteration_requests_are_bounded_and_references_are_valid():
    evaluation, context, tactics, utility = _evaluation()
    evaluation["iteration_requests"] = [{"request_type": "new_tactic", "reason": "Recovery is not covered", "target_scenario_ids": ["QS2"], "target_alternative_ids": ["A1"], "request_for_toulmin": "Propose a recovery mechanism", "status": "PENDING"}]
    assert validate_evaluation(evaluation, context, tactics, utility) == []
    evaluation["iteration_requests"][0]["target_scenario_ids"] = ["absent"]
    assert any("invalid target_scenario_ids" in error for error in validate_evaluation(evaluation, context, tactics, utility))


def test_evaluate_runs_bounded_toulmin_refinement_and_reevaluation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.init("codex") == 0
    root = tmp_path / ".kataliarc"
    context = {"business_goals": [], "business_requirements": [], "constraints": [], "quality_attributes": [], "quality_scenarios": [{"id": "QS1", "description": "P95 latency under 300 ms", "quality_attribute": "performance", "priority": "A", "mandatory": False}], "references": []}
    (root / "context.json").write_text(json.dumps(context), encoding="utf-8")
    (root / "utility-tree.json").write_text(json.dumps({"quality_attributes": [{"name": "performance", "scenario_ids": ["QS1"]}]}), encoding="utf-8")
    tactics = {"scenario_arguments": [], "tactics": [{"id": "T1", "name": "Cache"}], "pattern_tactic_interactions": [], "tactic_interactions": [], "alternatives": [{"id": "A1", "description": "Cache reads"}]}
    (root / "tactics.json").write_text(json.dumps(tactics), encoding="utf-8")
    config = json.loads((root / "config.json").read_text())
    config["language"] = "en"
    config["walton"] = {"max_iterations": 1}
    (root / "config.json").write_text(json.dumps(config), encoding="utf-8")
    initial, _, _, _ = _evaluation()
    initial["assessments"] = [_assessment("A1", "QS1")]
    initial["iteration_requests"] = [{"request_type": "new_tactic", "reason": "Recovery mechanism unclear", "target_scenario_ids": ["QS1"], "target_alternative_ids": ["A1"], "request_for_toulmin": "Clarify recovery"}]
    calls = []

    class Result:
        returncode = 0
        error = None

    class Provider:
        def run(self, agent, prompt, cwd):
            calls.append(prompt)
            if len(calls) == 1:
                (root / "evaluation.json").write_text(json.dumps(initial), encoding="utf-8")
            elif len(calls) == 3:
                revised = json.loads((root / "evaluation.json").read_text())
                revised["iteration_requests"] = []
                (root / "evaluation.json").write_text(json.dumps(revised), encoding="utf-8")
            return Result()

    monkeypatch.setattr(cli, "AgentProvider", Provider)
    assert cli.run_stage("evaluate", True) == 0
    assert len(calls) == 3
    assert "Walton requested a bounded refinement" in calls[1]
    final = json.loads((root / "evaluation.json").read_text())
    assert final["iteration"] == 1
    assert any(item["action"] == "toulmin_refinement" for item in final["iteration_history"])

