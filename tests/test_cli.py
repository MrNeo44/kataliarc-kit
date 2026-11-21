import json
import hashlib
from pathlib import Path
import subprocess
import sys
import io

import pytest

if sys.version_info < (3, 11):
    import tomli as tomllib
else:
    import tomllib

from kataliarc import cli
from kataliarc.providers import AgentProvider, AgentResult, CodexProvider
from kataliarc.adapters import ADAPTERS
from kataliarc.adapters.codex import CODEX_INSTRUCTIONS, CodexAdapter
from kataliarc.wizard import BANNER, render_banner, select_agent


def test_init_is_idempotent_and_installs_codex_integration(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.init("codex") == 0
    before = (tmp_path / ".kataliarc/context.json").read_text()
    assert cli.init("codex") == 0
    assert (tmp_path / ".kataliarc/context.json").read_text() == before
    instructions = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert instructions == CODEX_INSTRUCTIONS
    assert "delegate the requested work to the matching subagent" in instructions
    skill = tmp_path / ".agents/skills/kataliarc-pohl/SKILL.md"
    assert "name: kataliarc-pohl" in skill.read_text()
    assert "description:" in skill.read_text()
    for role in ("pohl", "toulmin", "walton"):
        path = tmp_path / ".codex/agents" / f"{role}.toml"
        agent = tomllib.loads(path.read_text(encoding="utf-8"))
        assert agent["name"] == role
        assert agent["description"]
        assert f"kataliarc-{role}" in agent["developer_instructions"]


@pytest.mark.parametrize("upgrade_command", ["init", "update"])
def test_codex_upgrade_adds_and_tracks_toulmin_and_walton(tmp_path, monkeypatch, capsys, upgrade_command):
    from kataliarc.management import doctor, update

    pohl = ".codex/agents/pohl.toml"
    old_instructions = "<!-- KatalIArc managed -->\nFollow the installed skills.\n"
    instructions = tmp_path / "AGENTS.md"
    with monkeypatch.context() as legacy:
        legacy.setattr(CodexAdapter, "extra_files", {pohl: CodexAdapter.extra_files[pohl]})
        legacy.setattr(CodexAdapter, "instruction_files", {"AGENTS.md": old_instructions})
        assert cli.init("codex", tmp_path) == 0
    original_pohl = (tmp_path / pohl).read_bytes()
    missing = [".codex/agents/toulmin.toml", ".codex/agents/walton.toml"]
    assert doctor(tmp_path) == 1
    report = capsys.readouterr().out
    assert all(relative in report for relative in missing)
    if upgrade_command == "init":
        assert cli.init("codex", tmp_path) == 0
        assert instructions.read_text(encoding="utf-8") == old_instructions
    else:
        assert update(tmp_path, dry_run=True) == 0
        report = capsys.readouterr().out
        assert "UPDATE AGENTS.md" in report
        assert instructions.read_text(encoding="utf-8") == old_instructions
        for relative in missing:
            assert f"UPDATE {relative}" in report
            assert not (tmp_path / relative).exists()
        assert update(tmp_path, yes=True) == 0
        assert instructions.read_text(encoding="utf-8") == CODEX_INSTRUCTIONS
    manifest = json.loads((tmp_path / ".kataliarc/managed-files.json").read_text(encoding="utf-8"))
    for relative in missing:
        assert manifest["files"][relative] == hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest()
    assert (tmp_path / pohl).read_bytes() == original_pohl
    assert doctor(tmp_path) == 0


def test_validate_accepts_empty_init(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.init("codex")
    assert cli.validate() == 0


def test_validate_checks_references_and_priorities(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.init("codex")
    ctx = Path(".kataliarc/context.json")
    data = json.loads(ctx.read_text())
    data["quality_scenarios"] = [{"id": "S1", "priority": "X"}]
    ctx.write_text(json.dumps(data))
    tactics = Path(".kataliarc/tactics.json")
    t = json.loads(tactics.read_text())
    t["scenario_arguments"] = [{"scenario_id": "S2", "claim": "x"}]
    tactics.write_text(json.dumps(t))
    assert cli.validate() == 1


def test_validate_checks_utility_tree_references_and_attribute_grouping(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.init("codex")
    context_path = Path(".kataliarc/context.json")
    context = json.loads(context_path.read_text())
    context["quality_scenarios"] = [{
        "id": "S1", "description": "Recover within 30 seconds", "quality_attribute": "availability",
        "priority": "pendiente", "mandatory": False,
    }]
    context_path.write_text(json.dumps(context), encoding="utf-8")
    tree_path = Path(".kataliarc/utility-tree.json")
    tree_path.write_text(json.dumps({"quality_attributes": [{"name": "performance", "scenario_ids": ["S1"]}]}), encoding="utf-8")
    assert cli.validate() == 1
    tree_path.write_text(json.dumps({"quality_attributes": [{"name": "availability", "scenario_ids": ["S1"]}]}), encoding="utf-8")
    assert cli.validate() == 0


def test_validate_accepts_legacy_utility_tree_as_references_and_recommends_conversion(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    cli.init("codex")
    context_path = Path(".kataliarc/context.json")
    context = json.loads(context_path.read_text())
    context["quality_scenarios"] = [{
        "id": "S1", "description": "Recover within 30 seconds", "quality_attribute": "availability",
        "priority": "pendiente", "mandatory": False,
    }]
    context_path.write_text(json.dumps(context), encoding="utf-8")
    tree_path = Path(".kataliarc/utility-tree.json")
    tree_path.write_text(json.dumps({"quality_attributes": [{"name": "availability", "scenarios": [{"id": "S1", "description": "old duplicate"}]}]}), encoding="utf-8")
    assert cli.validate() == 0
    assert "convert branches to scenario_ids" in capsys.readouterr().out


def test_help_entrypoint():
    env = dict(__import__("os").environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    result = subprocess.run([sys.executable, "-m", "kataliarc.cli", "--help"], capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert "pohl elicit" in result.stdout


def test_agent_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli.init("codex")
    monkeypatch.setattr("kataliarc.providers.shutil.which", lambda _: None)
    assert cli.run_stage("design", True) == 2


@pytest.mark.parametrize("provider", ["codex", "gemini"])
def test_elicitation_routes_to_pohl_subagent_only_in_codex(tmp_path, monkeypatch, provider):
    assert cli.init(provider, tmp_path, language="en") == 0
    calls = []

    def run(self, agent, prompt, cwd):
        calls.append((agent, prompt, cwd))
        return AgentResult(0)

    monkeypatch.setattr(AgentProvider, "run", run)
    assert cli.run_stage("elicit", True) == 0
    [(agent, prompt, cwd)] = calls
    assert (agent, cwd) == (provider, tmp_path)
    if provider == "codex":
        assert prompt.startswith("Delegate the phase below to the `pohl` subagent")
        assert "apply the `kataliarc-pohl` skill" in prompt
        assert prompt.endswith(cli.PROMPTS_EN["elicit"])
    else:
        assert prompt == cli.PROMPTS_EN["elicit"]


def test_codex_adapter_simulated(tmp_path, monkeypatch):
    monkeypatch.setattr("kataliarc.providers.shutil.which", lambda _: "/usr/bin/codex")
    calls = []

    class Result:
        returncode = 0

    def fake_run(args, cwd, check):
        calls.append((args, cwd, check))
        return Result()

    monkeypatch.setattr("kataliarc.providers.subprocess.run", fake_run)
    result = CodexProvider().run("revise artifacts", tmp_path)
    assert result.returncode == 0
    assert calls == [(["/usr/bin/codex", "exec", "revise artifacts"], tmp_path, False)]


def test_banner_exact_and_disabled():
    class TTY(io.StringIO):
        @property
        def encoding(self):
            return "utf-8"
        def isatty(self):
            return True
    stream = TTY()
    render_banner(stream)
    assert stream.getvalue() == BANNER + "\n\n"
    hidden = TTY()
    render_banner(hidden, enabled=False)
    assert hidden.getvalue() == ""


def test_selector_non_tty_choices():
    output = io.StringIO()
    assert select_agent(io.StringIO("3\n"), output) == "gemini"
    assert "OpenAI Codex" in output.getvalue()


def test_selector_arrow_navigation(monkeypatch):
    import kataliarc.wizard as wizard
    from prompt_toolkit.keys import Keys

    class FakeEvent:
        def __init__(self, app): self.app = app

    class FakeApplication:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            FakeApplication.last_app = self
        def run(self):
            bindings = self.kwargs["key_bindings"]
            down = bindings.get_bindings_for_keys((Keys.Down,))[0]
            down.handler(FakeEvent(self))
            control = self.kwargs["layout"].container.content
            fragments = control.text()
            self.rendered_after_down = "".join(fragment[1] for fragment in fragments)
            enter = bindings.get_bindings_for_keys((Keys.Enter,))[0]
            enter.handler(FakeEvent(self))
            return self.result
        def exit(self, *, result=None, exception=None): self.result = result

    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(wizard, "detect_agents", lambda: {"codex": "/bin/codex", "claude": None, "gemini": None, "copilot": "/bin/copilot"})
    monkeypatch.setattr(wizard, "Application", FakeApplication)

    class TerminalInput:
        def isatty(self): return True

    assert select_agent(TerminalInput(), io.StringIO()) == "claude"
    assert "● Claude Code (not installed)" in FakeApplication.last_app.rendered_after_down


def test_each_adapter_installs_native_skills_and_preserves_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    roots = {"codex": ".agents/skills", "claude": ".claude/skills", "gemini": ".gemini/skills", "copilot": ".github/skills"}
    for agent, skill_root in roots.items():
        target = tmp_path / skill_root / "kataliarc-pohl" / "SKILL.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("custom", encoding="utf-8")
        assert cli.init(agent) == 0
        assert target.read_text(encoding="utf-8") == "custom"
        assert (tmp_path / skill_root / "kataliarc-walton" / "SKILL.md").exists()
        assert json.loads((tmp_path / ".kataliarc/config.json").read_text())["agent"] == agent
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / "GEMINI.md").exists()
    assert (tmp_path / ".gemini/commands/kataliarc/status.toml").exists()
    assert (tmp_path / ".github/agents/kataliarc-review.agent.md").exists()
    assert tomllib.loads((tmp_path / ".gemini/commands/kataliarc/status.toml").read_text())["prompt"]
    copilot_agent = (tmp_path / ".github/agents/kataliarc-review.agent.md").read_text()
    assert copilot_agent.startswith("---\nname: kataliarc-review\ndescription:")
    assert "\n---\n" in copilot_agent


def test_skill_frontmatter_and_provider_specific_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for agent, adapter in ADAPTERS.items():
        assert cli.init(agent) == 0
        skill = tmp_path / adapter().skill_root / "kataliarc-walton" / "SKILL.md"
        content = skill.read_text(encoding="utf-8")
        assert content.startswith("---\nname: kataliarc-walton\ndescription:")
        assert "\n---\n" in content
        assert not (tmp_path / adapter().skill_root / "kataliarc-kazman").exists()


def test_init_noninteractive_no_banner_and_idempotent_user_data(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    assert cli.init("codex", no_banner=False) == 0
    context = tmp_path / ".kataliarc/context.json"
    context.write_text('{"preserved": true}\n', encoding="utf-8")
    custom = tmp_path / "AGENTS.md"
    custom.write_text("custom instructions\n", encoding="utf-8")
    assert cli.init("codex") == 0
    assert json.loads(context.read_text())["preserved"] is True
    assert custom.read_text() == "custom instructions\n"


def test_init_update_preserves_customized_skills_and_updates_managed_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert cli.init("gemini") == 0
    managed = tmp_path / "GEMINI.md"
    managed.write_text(managed.read_text() + "\nold generated text\n", encoding="utf-8")
    custom = tmp_path / ".gemini/skills/kataliarc-pohl/SKILL.md"
    custom.write_text("my edited skill", encoding="utf-8")
    user_file = tmp_path / "GEMINI.md.user-backup"
    user_file.write_text("untouched", encoding="utf-8")
    assert cli.init("gemini", overwrite=True) == 0
    assert "old generated text" not in managed.read_text(encoding="utf-8")
    assert custom.read_text(encoding="utf-8") == "my edited skill"
    assert user_file.read_text(encoding="utf-8") == "untouched"


def test_agent_provider_commands_and_missing_tool(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr("kataliarc.providers.shutil.which", lambda name: f"/bin/{name}")

    class Result:
        returncode = 0

    monkeypatch.setattr("kataliarc.providers.subprocess.run", lambda args, cwd, check: (calls.append(args) or Result()))
    for key, prefix in {"codex": "exec", "claude": "-p", "gemini": "-p", "copilot": "-p"}.items():
        assert AgentProvider().run(key, "prompt", tmp_path).returncode == 0
        assert calls[-1][1] == prefix
    monkeypatch.setattr("kataliarc.providers.shutil.which", lambda _: None)
    assert AgentProvider().run("gemini", "prompt", tmp_path).returncode == 2


def test_cli_init_flag_and_commands_help(tmp_path):
    env = dict(__import__("os").environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    init = subprocess.run([sys.executable, "-m", "kataliarc.cli", "init", "--agent", "claude", "--directory", str(tmp_path), "--no-banner"], capture_output=True, text=True, env=env)
    assert init.returncode == 0
    help_result = subprocess.run([sys.executable, "-m", "kataliarc.cli", "--help"], capture_output=True, text=True, env=env)
    assert help_result.returncode == 0
    for command in ("init", "pohl elicit", "toulmin design", "walton decide"):
        assert command in help_result.stdout
    for command in ("validate", "status", "decide", "doctor", "update"):
        topic = subprocess.run([sys.executable, "-m", "kataliarc.cli", "help", command], capture_output=True, text=True, env=env)
        assert topic.returncode == 0
        assert f"kataliarc {command}" in topic.stdout
    assert "kazman" not in help_result.stdout
    for retired_alias in ("elicit", "prioritize", "design", "evaluate", "review"):
        assert "{" + retired_alias not in help_result.stdout


def test_doctor_json_and_update_dry_run_and_conflict_preservation(tmp_path, monkeypatch, capsys):
    from kataliarc.management import doctor, update
    monkeypatch.chdir(tmp_path)
    assert cli.init("codex") == 0
    capsys.readouterr()
    assert doctor(tmp_path, as_json=True) == 0
    result = json.loads(capsys.readouterr().out)
    assert all(item["status"] in {"OK", "WARNING", "ERROR"} for item in result)
    skill = tmp_path / ".agents/skills/kataliarc-pohl/SKILL.md"
    skill.write_text("my local customization", encoding="utf-8")
    original = skill.read_text(encoding="utf-8")
    agent = tmp_path / ".codex/agents/walton.toml"
    custom_agent = agent.read_text(encoding="utf-8") + "\n# My local customization\n"
    agent.write_text(custom_agent, encoding="utf-8")
    assert update(tmp_path, dry_run=True, yes=True) == 0
    assert skill.read_text(encoding="utf-8") == original
    assert agent.read_text(encoding="utf-8") == custom_agent
    assert update(tmp_path, yes=True) == 0
    assert skill.read_text(encoding="utf-8") == original
    assert agent.read_text(encoding="utf-8") == custom_agent
    report = capsys.readouterr().out
    assert "CONFLICT (preserved) .agents/skills/kataliarc-pohl/SKILL.md" in report
    assert "CONFLICT (preserved) .codex/agents/walton.toml" in report


def test_doctor_is_read_only_and_configures_knowledge_paths(tmp_path, monkeypatch):
    from kataliarc.management import doctor
    monkeypatch.chdir(tmp_path)
    assert cli.init("gemini", language="en") == 0
    config = json.loads((tmp_path / ".kataliarc/config.json").read_text())
    config["knowledge_sources"] = [{"type": "local", "path": str(tmp_path / "missing"), "evidence_status": "unverified"}]
    (tmp_path / ".kataliarc/config.json").write_text(json.dumps(config))
    manifest = (tmp_path / ".kataliarc/managed-files.json").read_bytes()
    assert doctor(tmp_path) == 0
    assert (tmp_path / ".kataliarc/managed-files.json").read_bytes() == manifest


def test_update_updates_packaged_resources_and_backs_up(tmp_path, monkeypatch):
    from kataliarc.management import update
    monkeypatch.chdir(tmp_path)
    assert cli.init("claude") == 0
    managed = tmp_path / ".kataliarc/schemas/context.schema.json"
    resource = Path(cli.__file__).resolve().parent / "resources/schemas/context.schema.json"
    original = resource.read_bytes()
    resource.write_bytes(original + b"\n")
    try:
        assert update(tmp_path, yes=True) == 0
    finally:
        resource.write_bytes(original)
    assert managed.with_name("context.schema.json.kataliarc-backup").is_file()


def test_update_removes_unmodified_obsolete_kazman_skill(tmp_path, monkeypatch, capsys):
    from kataliarc.management import update
    monkeypatch.chdir(tmp_path)
    assert cli.init("codex") == 0
    capsys.readouterr()
    legacy_skill = tmp_path / ".agents/skills/kataliarc-kazman/SKILL.md"
    legacy_skill.parent.mkdir(parents=True)
    legacy_skill.write_text("<!-- KatalIArc managed -->\nold skill", encoding="utf-8")
    manifest_path = tmp_path / ".kataliarc/managed-files.json"
    manifest = json.loads(manifest_path.read_text())
    rel = str(legacy_skill.relative_to(tmp_path))
    manifest["files"][rel] = hashlib.sha256(legacy_skill.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    assert update(tmp_path, yes=True) == 0
    assert not legacy_skill.exists()
    assert rel not in json.loads(manifest_path.read_text())["files"]


def test_cli_all_workflow_commands_and_noninteractive_guard(tmp_path):
    env = dict(__import__("os").environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src"))
    init = subprocess.run([sys.executable, "-m", "kataliarc.cli", "init", "--agent", "copilot", "--directory", str(tmp_path), "--language", "en"], capture_output=True, text=True, env=env)
    assert init.returncode == 0
    for command in ("validate", "status"):
        result = subprocess.run([sys.executable, "-m", "kataliarc.cli", command], cwd=tmp_path, capture_output=True, text=True, env=env)
        assert result.returncode == 0, f"{command}: {result.stderr}"
    for role, action in (("pohl", "elicit"), ("pohl", "prioritize"), ("toulmin", "design"), ("walton", "evaluate"), ("walton", "review"), ("walton", "decide")):
        result = subprocess.run([sys.executable, "-m", "kataliarc.cli", role, action, "--help"], cwd=tmp_path, capture_output=True, text=True, env=env)
        assert result.returncode == 0, f"{role} {action}: {result.stderr}"
    assert subprocess.run([sys.executable, "-m", "kataliarc.cli", "kazman", "evaluate"], cwd=tmp_path, capture_output=True, text=True, env=env).returncode == 2
    for retired_alias in ("elicit", "prioritize", "design", "evaluate", "review"):
        result = subprocess.run([sys.executable, "-m", "kataliarc.cli", retired_alias], cwd=tmp_path, capture_output=True, text=True, env=env)
        assert result.returncode == 2, f"legacy alias {retired_alias} is still registered"
    assert subprocess.run([sys.executable, "-m", "kataliarc.cli", "decide", "--help"], cwd=tmp_path, capture_output=True, text=True, env=env).returncode == 0
    assert subprocess.run([sys.executable, "-m", "kataliarc.cli", "doctor", "--json"], cwd=tmp_path, capture_output=True, text=True, env=env).returncode == 0
    assert subprocess.run([sys.executable, "-m", "kataliarc.cli", "update", "--dry-run"], cwd=tmp_path, capture_output=True, text=True, env=env).returncode == 0
    missing = subprocess.run([sys.executable, "-m", "kataliarc.cli", "init"], cwd=tmp_path, input="", capture_output=True, text=True, env=env)
    assert missing.returncode == 2
    assert "indica --agent" in missing.stderr


def test_global_install_uses_user_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    assert cli.init("codex", tmp_path, global_scope=True) == 0
    assert (tmp_path / ".agents/skills/kataliarc-pohl/SKILL.md").is_file()
    assert (tmp_path / ".codex/AGENTS.md").read_text(encoding="utf-8") == CODEX_INSTRUCTIONS
    for role in ("pohl", "toulmin", "walton"):
        assert (tmp_path / ".codex/agents" / f"{role}.toml").is_file()
    config = json.loads((tmp_path / ".kataliarc/config.json").read_text())
    assert config["scope"] == "user"
