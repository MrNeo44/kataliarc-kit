import json
from pathlib import Path

import pytest

from kataliarc import cli
from kataliarc.adr import (
    create_proposals,
    load_adr,
    metadata_for,
    transition,
    update_indexing,
    validate_record,
)
from kataliarc.rag import RAGError
from kataliarc.toulmin import _accepted_adr_hits, build_toulmin_input
from kataliarc.evaluation import CRITERIA, RUBRIC_VERSION, finalize_evaluation


def initialize(tmp_path, monkeypatch, *, rag=False):
    monkeypatch.chdir(tmp_path)
    assert cli.init("codex", rag_vector_store_id="vs-test" if rag else None) == 0
    return tmp_path / ".kataliarc"


def prepare_analysis(root: Path):
    context = json.loads((root / "context.json").read_text())
    context["business_goals"] = ["Reduce checkout abandonment"]
    context["business_requirements"] = ["Checkout remains available"]
    context["constraints"] = ["Must preserve payment audit trail"]
    context["quality_scenarios"] = [{
        "id": "QA-01", "description": "Checkout recovers within 30 seconds", "quality_attribute": "availability",
        "priority": "A", "mandatory": False, "acceptance_criteria": "Recovery under 30s",
    }]
    (root / "context.json").write_text(json.dumps(context), encoding="utf-8")
    (root / "utility-tree.json").write_text(json.dumps({"quality_attributes": [{"name": "availability", "scenario_ids": ["QA-01"]}]}), encoding="utf-8")
    tactics = json.loads((root / "tactics.json").read_text())
    tactics["tactics"] = [{"id": "T-01", "name": "Health check", "source_refs": ["catalog:health-check"]}]
    tactics["scenario_arguments"] = [{
        "scenario_id": "QA-01", "claim": "Use health checks", "grounds": ["Failure detected"], "warrant": "Detection enables recovery",
        "backing": ["catalog entry"], "qualifier": "likely", "rebuttal": "Detection does not ensure recovery",
    }]
    tactics["alternatives"] = [{"id": "ALT-01", "description": "Replicated service"}, {"id": "ALT-02", "description": "Single service"}]
    (root / "tactics.json").write_text(json.dumps(tactics), encoding="utf-8")
    evaluation = json.loads((root / "evaluation.json").read_text())
    evaluation["rubric_version"] = RUBRIC_VERSION
    def assessment(alternative_id):
        return {
            "alternative_id": alternative_id, "scenario_id": "QA-01", "tactic_ids": ["T-01"],
            "criteria": {
                key: {"value": "CUMPLE", "justification": "The recorded scenario check supports the judgment.", "evidence_refs": [], "assumptions": []}
                for key in CRITERIA
            },
            "critical_question_assessments": [{
                "scheme": "causal_argument", "question": "Was failover tested?", "claim_ref": "QA-01/C4",
                "answer": "Further failover testing is desirable.", "result": "supported", "evidence_refs": [], "objection": None,
            }],
        }
    evaluation["assessments"] = [assessment("ALT-01"), assessment("ALT-02")]
    utility = json.loads((root / "utility-tree.json").read_text())
    evaluation = finalize_evaluation(evaluation, context, tactics, utility)
    (root / "evaluation.json").write_text(json.dumps(evaluation), encoding="utf-8")
    decision = json.loads((root / "decision.json").read_text())
    decision.update({"selected_alternative_id": "ALT-01", "status": "provisional", "rationale": "Best supported by current assessment.", "risks": ["Failover may lose in-flight work"], "tradeoffs": ["Higher operational complexity"]})
    (root / "decision.json").write_text(json.dumps(decision), encoding="utf-8")
    review = {"critical_questions": ["Was failover tested?"], "objections": [{"id": "W-01", "status": "open", "question": "What happens to in-flight payments?"}], "recommended_decision": "Adopt ALT-01 provisionally", "pending_verification": ["Run failover test"]}
    (root / "review.json").write_text(json.dumps(review), encoding="utf-8")


def create_one(root: Path):
    prepare_analysis(root)
    return create_proposals(root)[0]


def test_walton_review_persists_structured_proposed_adr(tmp_path, monkeypatch):
    root = initialize(tmp_path, monkeypatch)
    prepare_analysis(root)

    class Result:
        returncode = 0
        error = None

    class Provider:
        def run(self, agent, prompt, cwd):
            return Result()

    monkeypatch.setattr(cli, "AgentProvider", Provider)
    assert cli.run_stage("review", True) == 0
    adr = load_adr(root, "ADR-001")
    validate_record(adr)
    assert adr["status"] == "PROPOSED"
    assert adr["indexing"]["status"] == "NOT_REQUESTED"
    assert (root / "decisions/ADR-001.md").is_file()
    assert adr["current_version"]["sections"]["quality_scenarios"][0]["id"] == "QA-01"
    assert adr["current_version"]["sections"]["toulmin_arguments"][0]["claim"] == "Use health checks"
    assert "Was failover tested?" in adr["current_version"]["sections"]["walton_critical_questions"]
    sections = adr["current_version"]["sections"]
    assert {row["action"] for row in sections["alternative_results"]} == {"MANTENER"}
    assert sections["alternatives_considered"]["discarded"] == []


def test_proposed_and_rejected_adrs_are_never_indexed(tmp_path, monkeypatch):
    root = initialize(tmp_path, monkeypatch, rag=True)
    adr = create_one(root)
    assert adr["status"] == "PROPOSED"
    assert adr["indexing"]["status"] == "NOT_REQUESTED"
    assert cli.decide_action(reject="ADR-001", actor="reviewer", note="Needs a stronger recovery argument") == 0
    record = load_adr(root, "ADR-001")
    assert record["status"] == "REJECTED"
    assert record["indexing"]["status"] == "NOT_REQUESTED"
    assert record["approval_history"][0]["action"] == "REJECTED"


def test_acceptance_is_persisted_before_index_and_records_metadata(tmp_path, monkeypatch):
    root = initialize(tmp_path, monkeypatch, rag=True)
    create_one(root)
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    calls = []

    class FakeIndexer:
        def __init__(self, api_key, vector_store_id):
            assert (api_key, vector_store_id) == ("mock-key", "vs-test")
        def index_accepted_adr(self, **kwargs):
            calls.append(kwargs)
            kwargs["on_uploaded"]("file-remote-1")
            return {"file_id": "file-remote-1", "status": "completed"}

    monkeypatch.setattr(cli, "OpenAIVectorStoreRetriever", FakeIndexer)
    workers = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda command, **kwargs: workers.append((command, kwargs)))
    assert cli.decide_action(accept="ADR-001", actor="Diego") == 0
    record = load_adr(root, "ADR-001")
    assert record["status"] == "ACCEPTED"
    assert record["approval_history"][0]["actor"] == "Diego"
    assert record["approval_history"][0]["version"] == 1
    assert record["indexing"]["status"] == "PENDING"
    assert len(workers) == 1
    assert workers[0][0][-2:] == ["--index-adr-worker", "ADR-001"]
    assert calls == []  # Approval returns before any network/indexing work.
    assert cli._index_accepted_adr("ADR-001") == 0  # Simulate the detached worker.
    record = load_adr(root, "ADR-001")
    assert record["indexing"]["status"] == "INDEXED"
    assert record["indexing"]["file_id"] == "file-remote-1"
    attrs = calls[0]["attributes"]
    for key in ("adr_id", "adr_version", "project_id", "source_type", "decision_status", "accepted_at", "quality_scenario_ids", "tactic_ids", "rubric_version", "origin", "index_key"):
        assert key in attrs
    assert attrs["decision_status"] == "ACCEPTED"
    assert "QA-01" in calls[0]["document"]
    assert "T-01" in attrs["tactic_ids"]


def test_local_retry_of_indexed_version_is_idempotent(tmp_path, monkeypatch, capsys):
    root = initialize(tmp_path, monkeypatch, rag=True)
    create_one(root)
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    calls = []

    class FakeIndexer:
        def __init__(self, *args): pass
        def index_accepted_adr(self, **kwargs):
            calls.append(kwargs)
            return {"file_id": "file-remote-1", "status": "completed"}

    monkeypatch.setattr(cli, "OpenAIVectorStoreRetriever", FakeIndexer)
    workers = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda command, **kwargs: workers.append(command))
    assert cli.decide_action(accept="ADR-001", actor="approver") == 0
    assert load_adr(root, "ADR-001")["indexing"]["status"] == "PENDING"
    assert cli._index_accepted_adr("ADR-001") == 0
    assert cli.decide_action(retry_index="ADR-001") == 0
    assert len(calls) == 1
    assert len(workers) == 1
    assert "already INDEXED" in capsys.readouterr().out


def test_remote_index_failure_does_not_revert_acceptance_and_retry_recovers(tmp_path, monkeypatch):
    root = initialize(tmp_path, monkeypatch, rag=True)
    create_one(root)
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key")
    attempts = []

    class FakeIndexer:
        def __init__(self, *args): pass
        def index_accepted_adr(self, **kwargs):
            attempts.append(kwargs)
            if len(attempts) == 1:
                raise RAGError("simulated remote failure")
            return {"file_id": "file-retry-2", "status": "completed"}

    monkeypatch.setattr(cli, "OpenAIVectorStoreRetriever", FakeIndexer)
    workers = []
    monkeypatch.setattr(cli.subprocess, "Popen", lambda command, **kwargs: workers.append(command))
    assert cli.decide_action(accept="ADR-001", actor="approver") == 0
    assert cli._index_accepted_adr("ADR-001") == 1
    failed = load_adr(root, "ADR-001")
    assert failed["status"] == "ACCEPTED"
    assert failed["indexing"]["status"] == "FAILED"
    assert cli.decide_action(retry_index="ADR-001") == 0
    assert cli._index_accepted_adr("ADR-001") == 0
    assert len(workers) == 2
    recovered = load_adr(root, "ADR-001")
    assert recovered["status"] == "ACCEPTED"
    assert recovered["indexing"]["status"] == "INDEXED"


def test_request_changes_preserves_version_and_next_walton_run_adds_version(tmp_path, monkeypatch):
    root = initialize(tmp_path, monkeypatch)
    create_one(root)
    assert cli.decide_action(request_changes="ADR-001", actor="reviewer", note="Clarify rollback") == 0
    pending = load_adr(root, "ADR-001")
    assert pending["status"] == "UNDER_REVIEW"
    prepare_analysis(root)
    revised = create_proposals(root)[0]
    assert revised["adr_id"] == "ADR-001"
    assert len(revised["versions"]) == 2
    assert revised["current_version"]["version"] == 2
    assert revised["status"] == "PROPOSED"


def test_multiple_independent_proposals_receive_separate_adrs(tmp_path, monkeypatch):
    root = initialize(tmp_path, monkeypatch)
    prepare_analysis(root)
    (root / "review.json").write_text(json.dumps({"decision_proposals": [{"title": "Payment isolation"}, {"title": "Event retention"}]}), encoding="utf-8")
    records = create_proposals(root)
    assert [record["adr_id"] for record in records] == ["ADR-001", "ADR-002"]
    assert all(record["status"] == "PROPOSED" for record in records)


def test_cli_decide_show_and_history_expose_approval_and_versions(tmp_path, monkeypatch, capsys):
    root = initialize(tmp_path, monkeypatch)
    create_one(root)
    capsys.readouterr()
    assert cli.decide_action(request_changes="ADR-001", actor="reviewer", note="Please clarify") == 0
    capsys.readouterr()
    assert cli.decide_action(history="ADR-001") == 0
    history = json.loads(capsys.readouterr().out)
    assert history["lifecycle"][-1]["status"] == "UNDER_REVIEW"
    assert history["versions"][0]["version"] == 1
    assert cli.decide_action(show="ADR-001") == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["status"] == "UNDER_REVIEW"


def test_superseded_accepted_adr_is_not_retrieved_as_current(tmp_path, monkeypatch):
    root = initialize(tmp_path, monkeypatch)
    first = create_one(root)
    transition(root, first["adr_id"], "accept", actor="user")
    prepare_analysis(root)
    second = create_proposals(root)[0]
    transition(root, second["adr_id"], "accept", actor="user", supersedes=first["adr_id"])
    records = [load_adr(root, "ADR-001"), load_adr(root, "ADR-002")]
    hits = []
    for record in records:
        attrs = metadata_for(record, json.loads((root / "config.json").read_text())["project_id"])
        hits.append({"attributes": attrs, "text": record["adr_id"]})
    accepted = _accepted_adr_hits(hits, root)
    assert [hit["text"] for hit in accepted] == ["ADR-002"]
    assert records[0]["status"] == "SUPERSEDED"


def test_toulmin_retrieves_accepted_katalIarc_and_external_but_filters_proposed(tmp_path, monkeypatch):
    root = initialize(tmp_path, monkeypatch)
    proposed = create_one(root)
    context = json.loads((root / "context.json").read_text())
    context["quality_scenarios"] = [{"id": "QA-01", "quality_attribute": "availability", "description": "Recover"}]
    (root / "context.json").write_text(json.dumps(context), encoding="utf-8")
    # Create a second valid proposal with a remote-like accepted state without making an API request.
    (root / "review.json").write_text(json.dumps({"critical_questions": ["Is recovery tested?"], "recommended_decision": "Adopt ALT-01"}), encoding="utf-8")
    second = create_proposals(root)[0]
    transition(root, second["adr_id"], "accept", actor="reviewer")
    project_id = json.loads((root / "config.json").read_text())["project_id"]
    hit_proposed = {"file_id": "f1", "filename": "proposal.md", "score": 0.9, "text": "proposal must be excluded", "attributes": {"origin": "kataliarc", "decision_status": "PROPOSED", "adr_id": "ADR-001", "adr_version": 1, "project_id": project_id}}
    hit_accepted = {"file_id": "f2", "filename": "accepted.md", "score": 0.8, "text": "accepted historical claim", "attributes": {"origin": "kataliarc", "decision_status": "ACCEPTED", "adr_id": second["adr_id"], "adr_version": 1, "project_id": project_id}}
    hit_external = {"file_id": "f3", "filename": "external.md", "score": 0.7, "text": "external ADR", "attributes": {"source_type": "external_adr"}}

    class FakeSearch:
        def search(self, query, *, max_results=10):
            return [hit_proposed, hit_accepted, hit_external]

    result = build_toulmin_input(root, tmp_path, {"rag": {"enabled": True, "vector_store_id": "vs"}}, retriever=FakeSearch())
    texts = [item["text"] for item in result["rag"]["results"]]
    assert "proposal must be excluded" not in texts
    assert "accepted historical claim" in texts
    assert "external ADR" in texts


def test_walton_instructions_include_accepted_adr_critical_review():
    skill = Path(__file__).parents[1] / "src/kataliarc/templates/skills/walton/SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "toulmin-input.json" in text
    assert "Historical ADRs are contextual evidence" in text
    assert "transfer to the current design remains a hypothesis" in text


def test_remote_index_retry_finds_existing_stable_index_key_without_duplicate_upload():
    from kataliarc.rag import OpenAIVectorStoreRetriever

    index_key = "stable-index-key"
    calls = []

    class Response:
        def __init__(self, payload): self.payload = payload
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self): return json.dumps(self.payload).encode()

    def opener(request, timeout):
        calls.append(request)
        assert request.get_method() == "GET"
        return Response({"data": [{"id": "file-existing", "status": "completed", "attributes": {"index_key": index_key}}], "has_more": False})

    adapter = OpenAIVectorStoreRetriever("mock-key", "vs-test", opener=opener)
    result = adapter.index_accepted_adr(filename="ADR-001.md", document="Accepted ADR", attributes={"index_key": index_key})
    assert result["file_id"] == "file-existing"
    assert len(calls) == 1
