from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from kataliarc import cli
from kataliarc.evaluation import (
    CRITERIA,
    decide_alternative,
    finalize_evaluation,
    prepare_refinements,
    validate_evaluation,
    validate_rubric,
)


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def example():
    return json.loads((ROOT / "examples/walton-combination.json").read_text(encoding="utf-8"))


def inputs(example):
    return example["context"], example["tactics"], example["utility_tree"]


@pytest.mark.parametrize(("changed", "expected"), [
    ({}, ("MANTENER", "R4")),
    ({"C3": "REQUIERE_AJUSTE"}, ("MODIFICAR", "R3")),
    ({"C6": "INCIERTO"}, ("POSPONER", "R2")),
    ({"C1": "NO_CUMPLE"}, ("DESCARTAR", "R1")),
    ({"C1": "INCIERTO", "C6": "NO_CUMPLE"}, ("DESCARTAR", "R1")),
    ({"C1": "REQUIERE_AJUSTE", "C6": "INCIERTO"}, ("POSPONER", "R2")),
])
def test_deterministic_priority(changed, expected):
    values = dict.fromkeys(CRITERIA, "CUMPLE") | changed
    assert decide_alternative(values) == decide_alternative(dict(reversed(list(values.items())))) == expected


def test_engine_rejects_incomplete_or_unrecognized_judgments():
    values = dict.fromkeys(CRITERIA, "CUMPLE")
    with pytest.raises(ValueError, match="exactly"):
        decide_alternative({"C1": "CUMPLE"})
    with pytest.raises(ValueError, match="Invalid"):
        decide_alternative(values | {"C3": "MAYBE"})
    with pytest.raises(ValueError, match="Invalid"):
        decide_alternative(values | {"C3": 9})


def test_schema_and_example_agree_with_the_rules(example):
    rubric = json.loads((ROOT / "src/kataliarc/resources/metamodel/walton-rubric.json").read_text())
    assert validate_rubric(rubric) == []
    rubric["decision_rules"].reverse()
    assert validate_rubric(rubric)
    evaluation = example["evaluation"]
    assert validate_evaluation(evaluation, *inputs(example)) == []
    assert finalize_evaluation(evaluation, *inputs(example)) == evaluation
    assert evaluation["alternative_results"][0]["action"] == "MODIFICAR"


def test_forged_action_cannot_override_engine(example):
    evaluation = example["evaluation"]
    evaluation["alternative_results"] = [{"action": "MANTENER"}]
    assert validate_evaluation(evaluation, *inputs(example))
    derived = finalize_evaluation(evaluation, *inputs(example))
    assert derived["alternative_results"][0]["action"] == "MODIFICAR"


@pytest.mark.parametrize(("value", "required"), [
    ("REQUIERE_AJUSTE", "adjustment"),
    ("NO_CUMPLE", "impediment"),
    ("INCIERTO", "pending_information"),
])
def test_criterion_requires_specific_support(example, value, required):
    assessment = example["evaluation"]["assessments"][0]
    assessment["criteria"]["C1"]["value"] = value
    errors = validate_evaluation(example["evaluation"], *inputs(example))
    assert any(required in error for error in errors)


def test_no_cumple_requires_direct_evidence(example):
    judgment = example["evaluation"]["assessments"][0]["criteria"]["C1"]
    judgment.update(value="NO_CUMPLE", impediment="A documented mandatory condition prevents deployment.",
                    impediment_ref={"scenario_id": "QS-01"})
    judgment["evidence_refs"] = [{"kind": "ANALOGIA", "reference": "ADR-001"}]
    with pytest.raises(ValueError, match="evidence_refs"):
        finalize_evaluation(example["evaluation"], *inputs(example))


@pytest.mark.parametrize(("reference", "valid"), [
    ({"scenario_id": "QS-01"}, True),
    ({"scenario_id": "QS-02"}, False),
    ({"constraint_id": "CON-1"}, True),
    ({"constraint_id": "CON-2"}, False),
    ({"constraint_id": "missing"}, False),
])
def test_confirmed_blocker_must_reference_the_assessed_scenario_or_mandatory_constraint(example, reference, valid):
    example["context"]["constraints"] = [
        {"id": "CON-1", "mandatory": True}, {"id": "CON-2", "mandatory": False},
    ]
    draft = example["evaluation"]
    judgment = draft["assessments"][0]["criteria"]["C1"]
    judgment.update(value="NO_CUMPLE", impediment="A confirmed contradiction prevents deployment.",
                    impediment_ref=reference, evidence_refs=[{"kind": "DIRECTA", "reference": "EV-CONTRADICTION"}])
    if valid:
        assert finalize_evaluation(draft, *inputs(example))["alternative_results"][0]["action"] == "DESCARTAR"
    else:
        with pytest.raises(ValueError, match="impediment_ref"):
            finalize_evaluation(draft, *inputs(example))


def test_atam_risk_alone_does_not_discard_an_alternative(example):
    draft = example["evaluation"]
    assert draft["risks"]
    assert finalize_evaluation(draft, *inputs(example))["alternative_results"][0]["action"] == "MODIFICAR"
    draft["assessments"][0]["criteria"]["C4"]["value"] = "CUMPLE"
    assert finalize_evaluation(draft, *inputs(example))["alternative_results"][0]["action"] == "MANTENER"


def test_unresolved_objection_postpones_instead_of_refuting(example):
    draft = example["evaluation"]
    row = draft["assessments"][0]
    row["critical_question_assessments"][0]["result"] = "unresolved"
    row["criteria"]["C6"].update(value="INCIERTO", pending_information=["Resolve the cold-rollout analogy with a load test."])
    result = finalize_evaluation(draft, *inputs(example))["alternative_results"][0]
    assert (result["action"], result["rule"]) == ("POSPONER", "R2")
    row["criteria"]["C6"]["value"] = "NO_CUMPLE"
    with pytest.raises(ValueError, match="impediment"):
        finalize_evaluation(draft, *inputs(example))


def test_assessments_cover_affected_scenarios_and_combination_membership(example):
    evaluation = example["evaluation"]
    example["context"]["quality_scenarios"][1]["priority"] = "pendiente"
    example["context"]["quality_scenarios"][1]["mandatory"] = False
    example["utility_tree"]["quality_attributes"].pop()
    evaluation["assessments"].pop()
    errors = validate_evaluation(evaluation, *inputs(example))
    assert any("missing alternative/scenario coverage: ALT-003/QS-02" in error for error in errors)
    evaluation["assessments"][0]["tactic_ids"] = ["T-SCALE"]
    assert any("full set of tactics" in error for error in validate_evaluation(evaluation, *inputs(example)))


def test_combination_is_independent_from_its_components(example):
    evaluation = example["evaluation"]
    for alternative, member in (("ALT-001", "T-SCALE"), ("ALT-002", "T-CACHE")):
        example["tactics"]["alternatives"].append({"id": alternative, "tactic_ids": [member]})
        for source in evaluation["assessments"][:2]:
            row = deepcopy(source)
            row.update(alternative_id=alternative, tactic_ids=[member])
            row["criteria"]["C4"].update(value="INCIERTO", pending_information=["Measure the component independently."])
            evaluation["assessments"].append(row)
    results = finalize_evaluation(evaluation, *inputs(example))["alternative_results"]
    assert {item["alternative_id"]: item["action"] for item in results} == {
        "ALT-001": "POSPONER", "ALT-002": "POSPONER", "ALT-003": "MODIFICAR",
    }


def test_findings_and_walton_objections_are_validated(example):
    evaluation = example["evaluation"]
    evaluation["tradeoffs"][0]["affected_scenario_ids"] = ["QS-01", "missing"]
    assert any("ALT-003/missing" in error for error in validate_evaluation(evaluation, *inputs(example)))
    examination = evaluation["assessments"][0]["critical_question_assessments"][0]
    examination["objection"] = None
    assert any("objection" in error for error in validate_evaluation(evaluation, *inputs(example)))


def test_only_modifications_get_pending_refinements(example):
    assessment = example["evaluation"]["assessments"][0]
    assessment["criteria"]["C2"].update(value="INCIERTO", pending_information=["Measure the version service load."])
    result = finalize_evaluation(example["evaluation"], *inputs(example))
    prepare_refinements(result)
    assert result["alternative_results"][0]["action"] == "POSPONER"
    assert result["iteration_requests"][0]["status"] == "UNRESOLVED"


def _write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _initialize(tmp_path, monkeypatch, example):
    monkeypatch.chdir(tmp_path)
    assert cli.init("codex") == 0
    root = tmp_path / ".kataliarc"
    for filename, data in zip(("context.json", "tactics.json", "utility-tree.json"), inputs(example)):
        _write(root / filename, data)
    _write(root / "evaluation.json", example["evaluation"])
    return root


def test_finalize_cli_runs_without_provider_and_records_markdown(tmp_path, monkeypatch, example):
    root = _initialize(tmp_path, monkeypatch, example)
    draft = example["evaluation"]
    draft.pop("alternative_results")
    _write(root / "evaluation.json", draft)
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, (str(ROOT / "src"), os.environ.get("PYTHONPATH"))))}
    result = subprocess.run([sys.executable, "-m", "kataliarc.cli", "walton", "evaluate", "--finalize"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "ALT-003 MODIFICAR (R3)" in result.stdout
    assert "**MODIFICAR** (R3)" in (root / "evaluation.md").read_text()
    output = json.loads((root / "evaluation.json").read_text())
    assert output["alternative_results"][0]["action"] == "MODIFICAR"
    result = subprocess.run([sys.executable, "-m", "kataliarc.cli", "validate"], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_evaluate_runs_bounded_toulmin_refinement_and_reevaluation(tmp_path, monkeypatch, example):
    root = _initialize(tmp_path, monkeypatch, example)
    config = json.loads((root / "config.json").read_text())
    config["walton"] = {"max_iterations": 1}
    _write(root / "config.json", config)
    calls = []

    class Provider:
        def run(self, agent, prompt, cwd):
            calls.append(prompt)
            if len(calls) == 1:
                draft = deepcopy(example["evaluation"])
                draft["alternative_results"][0]["action"] = "DESCARTAR"
                _write(root / "evaluation.json", draft)
            if len(calls) == 3:
                revised = json.loads((root / "evaluation.json").read_text())
                revised["assessments"][0]["criteria"]["C4"].update(value="CUMPLE", justification="The recorded rollout check now supports sufficiency.")
                _write(root / "evaluation.json", revised)
            return cli.AgentResult(0)

    monkeypatch.setattr(cli, "AgentProvider", Provider)
    assert cli.run_stage("evaluate", True) == 0
    assert len(calls) == 3
    assert calls[0].startswith("Delegate the phase below to the `walton` subagent")
    assert calls[1].startswith("Delegate the phase below to the `toulmin` subagent")
    assert "Walton requested a bounded refinement" in calls[1]
    assert "Preserve unaffected assessments." in calls[2]
    final = json.loads((root / "evaluation.json").read_text())
    assert final["iteration"] == 1
    assert final["alternative_results"][0]["action"] == "MANTENER"
    assert final["assessment_history"][0]["alternative_results"][0]["action"] == "MODIFICAR"


def test_decide_restores_computed_outcomes_if_provider_edits_evaluation(tmp_path, monkeypatch, example):
    root = _initialize(tmp_path, monkeypatch, example)

    class Provider:
        def run(self, agent, prompt, cwd):
            overwritten = deepcopy(example["evaluation"])
            overwritten["alternative_results"][0]["action"] = "MANTENER"
            _write(root / "evaluation.json", overwritten)
            return cli.AgentResult(0)

    monkeypatch.setattr(cli, "AgentProvider", Provider)
    assert cli.run_stage("decide", True) == 1
    assert json.loads((root / "evaluation.json").read_text()) == example["evaluation"]


def test_decide_leaves_a_modifiable_alternative_unselected(tmp_path, monkeypatch, example):
    root = _initialize(tmp_path, monkeypatch, example)

    class Provider:
        def run(self, agent, prompt, cwd):
            _write(root / "decision.json", {"selected_alternative_id": "ALT-003"})
            return cli.AgentResult(0)

    monkeypatch.setattr(cli, "AgentProvider", Provider)
    assert cli.run_stage("decide", True) == 1
    assert json.loads((root / "decision.json").read_text())["selected_alternative_id"] is None


def test_review_copies_calculated_results_and_evidence_into_proposed_adr(tmp_path, monkeypatch, example):
    root = _initialize(tmp_path, monkeypatch, example)

    class Provider:
        def run(self, agent, prompt, cwd):
            _write(root / "review.json", example["review"])
            return cli.AgentResult(0)

    monkeypatch.setattr(cli, "AgentProvider", Provider)
    assert cli.run_stage("review", True) == 0
    adr = json.loads((root / "decisions/ADR-001.json").read_text())
    sections = adr["current_version"]["sections"]
    assert adr["status"] == "PROPOSED" and adr["indexing"]["status"] == "NOT_REQUESTED"
    assert sections["alternative_results"] == example["evaluation"]["alternative_results"]
    assert sections["risks_and_sensitivities"]["no_risks"][0]["id"] == "NR-01"
    assert sections["qualitative_scenario_assessments"][0]["criteria"]["C2"]["evidence_refs"][-1]["adr_id"] == "ADR-007"
    assert sections["pending_verification"]["rubric"][0]["criterion"] == "C4"


def test_reevaluation_preserves_legacy_judgments_without_translating_them(tmp_path, monkeypatch, example):
    root = _initialize(tmp_path, monkeypatch, example)
    previous = {"rubric_version": "legacy", "assessments": [{"alternative_id": "ALT-003", "scenario_id": "QS-01", "judgment": "legacy judgment"}]}
    _write(root / "evaluation.json", previous)
    _write(root / "config.json", {"agent": "codex", "walton": {"max_iterations": 0}})

    class Provider:
        def run(self, agent, prompt, cwd):
            _write(root / "evaluation.json", example["evaluation"])
            return cli.AgentResult(0)

    monkeypatch.setattr(cli, "AgentProvider", Provider)
    assert cli.run_stage("evaluate", True) == 0
    evaluation = json.loads((root / "evaluation.json").read_text())
    assert evaluation["assessment_history"] == [previous]
    assert evaluation["alternative_results"][0]["action"] == "MODIFICAR"
    assert evaluation["iteration_requests"][0]["status"] == "UNRESOLVED"
