# KatalIArc Kit

A cross-platform CLI for traceable software architecture decisions using quality scenarios, tactics, high-level patterns, structured arguments, and qualitative evaluation. Its methodology is shared across Codex, Claude Code, Gemini CLI, and GitHub Copilot. Toulmin can search a configured OpenAI vector store; after explicit user approval, KatalIArc can add accepted ADR projections to that store. Local ADR JSON and Markdown remain authoritative. It does not implement formal ATAM or automated compliance inference.

## Installation

Python 3.11 or later:

```sh
python3 -m pip install kataliarc-kit
```

For development from this repository:

```sh
python3 -m pip install -e .
kataliarc --help
```

## Initialization

In an interactive terminal, `kataliarc init` guides you through five steps: agent, location, language, optional knowledge sources, and confirmation. Knowledge source paths are recorded as unverified; they are not indexed or treated as validated evidence.

```text
Select your AI coding agent:

  > OpenAI Codex (installed)
    Claude Code (not installed)
    Gemini CLI (installed)
    GitHub Copilot (not installed)

Use ↑ ↓ to navigate and Enter to select.
```

Detection only reports availability. Files can still be generated when the provider's CLI is not installed. In a non-interactive terminal, specify the agent explicitly:

```sh
kataliarc init --agent codex --directory . --language en
kataliarc init --agent claude --directory ../service --language en
kataliarc init --agent gemini --global --language en
kataliarc init --agent copilot --knowledge-dir ./docs/adr
```

Generated artifacts and requested responses support English (`en`) and Spanish (`es`); Spanish is the default. JSON field names and contracts do not change between languages. Use `--no-banner` to suppress the banner.

## Integrations

KatalIArc installs three skills—Pohl, Toulmin, and Walton—in each provider's skill directory, along with project instructions. Walton owns scenario evaluation, Walton-style critical review, and recommendations. Codex uses `AGENTS.md`; Claude Code uses `CLAUDE.md`; Gemini CLI uses `GEMINI.md` and a TOML command; GitHub Copilot for VS Code uses `.github/copilot-instructions.md`, skills, and a custom agent definition. KatalIArc does not install or authenticate provider software. Methodological role/action commands invoke the configured local CLI and require separate authentication.

## Commands

```sh
kataliarc pohl elicit
kataliarc pohl prioritize
kataliarc toulmin design
kataliarc walton evaluate
kataliarc walton review
kataliarc walton decide
kataliarc decide --help
kataliarc validate
kataliarc status
kataliarc rag-test --query "latency and cache invalidation"
kataliarc doctor
kataliarc doctor --json
kataliarc doctor --global
kataliarc update --dry-run
kataliarc update
kataliarc update --yes
kataliarc update --global --dry-run
```

### Command responsibilities

| Command | What it does | Methodological skill |
| --- | --- | --- |
| `init` | Sets up the project and installs the skills | None; configures the selected provider |
| `pohl elicit` | Collects context and quality scenarios | Pohl |
| `pohl prioritize` | Organizes the utility tree and priorities | Pohl, with client confirmation |
| `toulmin design` | Proposes tactics and argued alternatives | Toulmin |
| `walton evaluate` | Evaluates scenarios and trade-offs | Walton |
| `walton review` | Critiques argument quality with Walton's critical questions | Walton |
| `walton decide` | Integrates the review and recommends a decision | Walton |
| `validate` | Checks artifact structure and some references | None; automatic validation |
| `status` | Shows artifact status | None; local status check |
| `rag-test` | Makes one read-only search against the configured ADR vector store | None; diagnostic query only |
| `doctor` | Diagnoses the installation and its resources | None; automatic diagnostics |
| `update` | Updates KatalIArc-managed resources | None; automatic maintenance |

The canonical role/action form invokes the provider configured by `init` directly:

```sh
kataliarc pohl elicit
kataliarc pohl prioritize
kataliarc toulmin design --repo ../service
kataliarc walton evaluate
kataliarc walton review
kataliarc walton decide
```

### ADR proposal and approval

After a successful `kataliarc walton review`, KatalIArc creates versioned `.kataliarc/decisions/ADR-NNN.json` and `.md` files in `PROPOSED` state from the review, context, tactics, and evaluation artifacts. Walton cannot approve a proposal. Inspect it with `kataliarc decide --show ADR-001`; view lifecycle, approval, version, and indexing history with `kataliarc decide --history ADR-001`.

Explicit approval is the only action that starts indexing:

```sh
kataliarc decide --accept ADR-001 --approver "Reviewer name"
kataliarc decide --reject ADR-001 --note "Reason"
kataliarc decide --request-changes ADR-001 --note "Clarify failover consequences"
kataliarc decide --retry-index ADR-001
kataliarc decide --accept ADR-002 --supersedes ADR-001
```

Indexing runs asynchronously in a detached local worker; approval returns while the ADR's indexing status is `PENDING` or `INDEXING`. Check progress with `kataliarc decide --show ADR-001` or `kataliarc status`. If indexing fails, the ADR remains `ACCEPTED` and its independent indexing status becomes `FAILED`; retry with `--retry-index`. KatalIArc stores the complete ADR locally and indexes a retrieval projection with origin, version, approval, scenario, tactic, and rubric metadata. Rejected and proposed ADRs are never indexed. Superseded ADRs remain in local history and are marked so Toulmin does not treat them as current. Acceptance records the user's choice; it does not prove empirical compliance. The evaluation stored in the ADR is a qualitative NFR/GRL-oriented scenario assessment, not a formal ATAM result.

### Using Pohl

1. Put stakeholder notes and context in `.kataliarc/context.md`.
2. Run `kataliarc pohl elicit`. Review the structured information and scenarios in `.kataliarc/context.json`; unresolved information stays marked as unknown rather than being invented.
3. Confirm scenario priorities with the client representative, then run `kataliarc pohl prioritize`. Confirmed priorities are stored in `context.json`; `utility-tree.json` only groups scenario IDs by quality attribute.
4. Run `kataliarc validate` to check the scenario references, then continue with `kataliarc toulmin design`.

`context.json` is the source of truth for scenario descriptions and priorities. `utility-tree.json` contains references only; it does not duplicate scenario descriptions or priorities.

The role determines the methodological skill, and the action determines the phase. Only the pairs shown in the command table are valid. Methodological commands invoke the configured provider. Only the Toulmin `design` action prepares repository evidence and performs RAG retrieval for architecture work; `rag-test` is a separate one-query connection diagnostic and does not invoke a methodological agent.

### What each skill takes from the process and metamodel

| Skill | Process responsibility | Main metamodel concepts | Handoff |
| --- | --- | --- | --- |
| Pohl | Elicit stakeholder context, business problem/goals/requirements, constraints, drivers, and quality scenarios; expose gaps and confirm priorities | `Stakeholder`, `BusinessProblem`, `BusinessGoal`, `BusinessRequirement`, `ArchitecturalProblem`, `ArchitecturalConstraint`, `ArchitecturalDriver`, `QualityScenario`, `UtilityTreeBranch` | Toulmin receives traceable scenarios and constraints; priorities remain in `context.json` |
| Toulmin | Generate tactics, arguments, interactions, and assembled alternatives | `ArchitecturalTactic`, `ArchitecturalPattern`, `ArchitecturalArgument`, `ArchitecturalAlternative` | Walton evaluates the alternatives |
| Walton | Assess alternatives against scenarios, compare trade-offs, critique argument quality, and recommend a decision | `ScenarioAssessment`, `DecisionOutcome`, `ArchitecturalArgument`, `ArchitecturalRisk`, `TradeOff` | User or authorized decision maker accepts, rejects, or requests changes |

Each skill file states its scope, inputs, outputs, and handoff. KatalIArc installs the machine-readable domain vocabulary in `.kataliarc/metamodel/domain.json`, its entity diagram in `domain.mmd`, the process guidance in `process.md`, and its activity diagram in `process.mmd`. `domain.json` is the single metamodel source; schemas validate the structure of individual artifacts, including ADRs. Each skill is instructed to read the shared process and use only its relevant concepts.

### Toulmin design and historical ADR search

Run design from the KatalIArc project directory. `--repo` selects a separate repository for bounded, read-only inspection; it is never modified. Before invoking the provider, KatalIArc writes `.kataliarc/repository-analysis.json` and `.kataliarc/toulmin-input.json`. These are reviewable inputs containing file/line references, candidate tactics, and any historical ADR excerpts returned by search.

Configure an existing OpenAI vector store with `kataliarc init --agent codex --rag-vector-store-id vs_...`, by setting `OPENAI_VECTOR_STORE_ID` in the process environment or the KatalIArc project's `.env`, or by adding `{"rag": {"vector_store_id": "vs_..."}}` to `.kataliarc/config.json`. Set `OPENAI_API_KEY` in the environment or project `.env` as well. Keep credentials out of source control. KatalIArc sends bounded text queries to the OpenAI vector-store search endpoint during `kataliarc toulmin design`; use `--no-rag` to skip those requests. Search failures leave the workflow usable and are reported as warnings. When no vector store is configured, Toulmin proceeds with repository and scenario evidence only.

To check connectivity without invoking a provider or running the full design phase, use `kataliarc rag-test --query "your architecture question"`. It makes exactly one search request and prints the matching ADR identifiers or filenames and scores, without dumping the retrieved text. Use `--max-results 1` for a very small response (allowed range: 1–5).

```sh
kataliarc toulmin design --repo ../service
kataliarc toulmin design --repo ../service --no-rag
```

Historical ADRs provide context, not proof that a past decision fits the current repository. The prepared input preserves source IDs and marks transfer to the current design as an inference/hypothesis. Retrieved content is treated as untrusted data. The provider is instructed to include all six Toulmin elements, including backing, and to leave final evaluation and decision to later phases.

`doctor` checks the provider, resources, JSON files, schemas, metamodel, knowledge paths, and permissions without writing files. `--json` produces JSON output without a banner or ANSI formatting. `update` only updates local resources listed in `.kataliarc/managed-files.json`; it reports conflicts, preserves conflicting files, and creates a `.kataliarc-backup` copy when updating a previously intact resource. `--dry-run` makes no changes; `--yes` enables non-interactive updates. KatalIArc does not download files from GitHub.

Architecture workflow artifacts are written to `.kataliarc/` for review. The client representative must confirm priorities. Hypotheses are not treated as evidence, and contribution is recorded separately from compliance.

`context.json` is the source of truth for quality scenario descriptions and priorities. `utility-tree.json` only groups scenario IDs under quality-attribute branches; it does not repeat descriptions or priority values. `kataliarc validate` checks that each tree reference exists and is grouped under the scenario's attribute.

## Troubleshooting

- **`--agent` is required in a non-interactive terminal:** use `kataliarc init --agent codex` (or `claude`, `gemini`, or `copilot`).
- **The provider is not on `PATH`:** skills can still be installed; install and authenticate the provider CLI separately before running a methodological role/action command.
- **Update conflicts:** run `doctor` to inspect the state, review files marked `CONFLICT`, and run `update` again when you want to adopt available changes.
- **Knowledge source paths do not exist:** correct the paths in `.kataliarc/config.json`; KatalIArc only records them.

## Development and tests

```sh
python3 -m pip install -e '.[test]'
python3 -m pytest
```
