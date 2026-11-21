import json
from pathlib import Path

from kataliarc import cli
from kataliarc.rag import OpenAIVectorStoreRetriever
from kataliarc.toulmin import build_toulmin_input


class FakeRetriever:
    def __init__(self):
        self.queries = []

    def search(self, query, *, max_results=10):
        self.queries.append((query, max_results))
        return [{
            "file_id": "file-adr-1",
            "filename": "ADR-001.md",
            "score": 0.82,
            "text": "Historical decision: use a cache with bounded invalidation.",
            "source_ref": {"filename": "ADR-001.md"},
        }]


def test_toulmin_retrieves_by_scenario_and_candidate_tactic_and_preserves_provenance(tmp_path):
    artifacts = tmp_path / ".kataliarc"
    artifacts.mkdir()
    (artifacts / "context.json").write_text(json.dumps({
        "constraints": ["Must keep data consistent"],
        "quality_scenarios": [{"id": "S1", "quality_attribute": "performance", "description": "P95 under 200ms"}],
    }), encoding="utf-8")
    retriever = FakeRetriever()
    result = build_toulmin_input(
        artifacts,
        tmp_path,
        {"rag": {"enabled": True, "vector_store_id": "vs-test", "max_results": 3}},
        retriever=retriever,
    )

    assert retriever.queries
    assert "scenario" in retriever.queries[0][0].lower()
    assert any("Architectural tactic mechanism" in query for query, _ in retriever.queries)
    assert result["rag"]["status"] == "retrieved"
    evidence = result["rag"]["results"][0]
    assert evidence["historical_claim_status"] == "documentada"
    assert evidence["transfer_to_current_repository_status"] == "inferencia/hipótesis"
    assert len(evidence["retrieved_via"]) > 1
    assert result["safety"]["rag_store_was_modified"] is False


def test_utility_tree_references_context_scenarios_without_copying_them(tmp_path):
    from kataliarc.toulmin import collect_scenarios

    (tmp_path / "context.json").write_text(json.dumps({
        "constraints": [],
        "quality_scenarios": [{"id": "S1", "quality_attribute": "availability", "description": "Recover within 30s", "priority": "pendiente", "mandatory": False}],
    }), encoding="utf-8")
    (tmp_path / "utility-tree.json").write_text(json.dumps({
        "quality_attributes": [{"name": "availability", "scenario_ids": ["S1"]}],
    }), encoding="utf-8")
    scenarios, _, _ = collect_scenarios(tmp_path)
    assert len(scenarios) == 1
    assert scenarios[0]["priority"] == "pendiente"
    assert scenarios[0]["mandatory"] is False
    assert scenarios[0]["origins"] == ["context.json", "utility-tree.json"]


def test_repository_scan_skips_environment_secrets_and_never_executes_code(tmp_path):
    artifacts = tmp_path / ".kataliarc"
    artifacts.mkdir()
    (tmp_path / "app.py").write_text("class Service:\n    pass\n", encoding="utf-8")
    (tmp_path / ".env").write_text("OPENAI_API_KEY=must-not-appear\n", encoding="utf-8")
    result = build_toulmin_input(artifacts, tmp_path, {"rag": {"enabled": False}})
    serialized = json.dumps(result)
    assert "must-not-appear" not in serialized
    assert ".env" not in serialized
    assert result["safety"]["repository_code_was_executed"] is False
    assert result["repository"]["read_only"] is True
    assert result["repository"]["findings"]


def test_vector_store_adapter_posts_to_search_endpoint_with_bounded_request():
    calls = []

    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return json.dumps({"data": [{"file_id": "f1", "filename": "ADR.md", "score": 0.7, "content": [{"type": "text", "text": "Decision"}]}]}).encode()

    def opener(request, timeout):
        calls.append((request, timeout))
        return Response()

    retriever = OpenAIVectorStoreRetriever("secret", "vs/id", opener=opener)
    result = retriever.search("scenario", max_results=7)
    request, _ = calls[0]
    assert request.full_url.endswith("/v1/vector_stores/vs%2Fid/search")
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"query": "scenario", "max_num_results": 7}
    assert result[0]["text"] == "Decision"
    assert "secret" not in json.dumps(result)


def test_design_cli_prepares_inputs_and_invokes_provider_only_for_design(tmp_path, monkeypatch):
    project = tmp_path / "kataliarc-project"
    repo = tmp_path / "service"
    project.mkdir()
    repo.mkdir()
    monkeypatch.chdir(project)
    cli.init("codex", language="en")
    (repo / "README.md").write_text("Service architecture overview", encoding="utf-8")
    (repo / "main.py").write_text("class Service:\n    pass\n", encoding="utf-8")
    calls = []

    class ProviderResult:
        returncode = 0
        error = None

    class Provider:
        def run(self, agent, prompt, cwd):
            calls.append((agent, prompt, cwd))
            return ProviderResult()

    monkeypatch.setattr(cli, "AgentProvider", Provider)
    assert cli.run_stage("design", True, repository=repo, rag_enabled=False) == 0
    assert calls and "toulmin-input.json" in calls[0][1]
    assert calls[0][1].startswith("Delegate the phase below to the `toulmin` subagent")
    assert calls[0][2] == project
    package = json.loads((project / ".kataliarc/toulmin-input.json").read_text())
    assert package["rag"]["status"] == "disabled"
    assert package["repository"]["repository_path"] == str(repo.resolve())
    assert cli.run_stage("evaluate", False) == 0
    assert len(calls) == 1


def test_init_accepts_vector_store_id_without_persisting_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.init("codex", rag_vector_store_id="vs-example") == 0
    config = json.loads((tmp_path / ".kataliarc/config.json").read_text(encoding="utf-8"))
    assert config["rag"]["vector_store_id"] == "vs-example"
    assert "api_key" not in json.dumps(config).lower()


def test_rag_test_makes_one_query_without_invoking_an_agent(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.init("codex", rag_vector_store_id="vs-example") == 0
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    calls = []

    class FakeSearch:
        def __init__(self, api_key, vector_store_id):
            assert api_key == "test-key"
            assert vector_store_id == "vs-example"
        def search(self, query, *, max_results):
            calls.append((query, max_results))
            return [{"adr_id": "ADR-007", "filename": "ADR-007.md", "score": 0.9, "text": "not printed"}]

    monkeypatch.setattr(cli, "OpenAIVectorStoreRetriever", FakeSearch)
    assert cli.rag_test("cache latency", 1) == 0
    output = capsys.readouterr().out
    assert calls == [("cache latency", 1)]
    assert "ADR-007" in output
    assert "not printed" not in output


def test_rag_test_fails_without_store_id_or_api_key_without_network(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert cli.init("codex") == 0
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.rag_test("test") == 2
    assert "No vector store ID configured" in capsys.readouterr().err


def test_role_action_cli_routes_toulmin_design_to_configured_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.init("gemini")
    calls = []
    monkeypatch.setattr(cli, "run_stage", lambda stage, with_agent, **kwargs: calls.append((stage, with_agent, kwargs)) or 0)
    monkeypatch.setattr("sys.argv", ["kataliarc", "toulmin", "design", "--repo", str(tmp_path), "--no-rag"])
    try:
        cli.main()
    except SystemExit as exc:
        assert exc.code == 0
    assert calls == [("design", True, {"repository": Path(tmp_path), "rag_enabled": False})]


def test_role_action_cli_rejects_unmapped_pair():
    import pytest
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["pohl", "design"])
    assert exc.value.code == 2
