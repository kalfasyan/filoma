# Adoption Roadmap: Dataset CI for ML

> **Status:** Proposal / planning document. Phases are ordered by leverage,
> not by chronology. Effort estimates are rough order-of-magnitude
> (S = ≤1 day, M = 2–5 days, L = 1–2 weeks, XL = >2 weeks).

This document is the plan for raising `filoma`'s adoption among newcomers. It
was written in response to the prompt:

> *"Make a plan for improving the adoption rate of this library to newcomers,
> focusing more on agentic features and ease of use."*

It is intentionally a **phased roadmap**, not an implementation. New agentic
capabilities (RAG, schema-proposing agents, etc.) are scoped here as **future
work only** — no code is changed by this document.

---

## 1. Positioning: the novelty hook

Today, `filoma` advertises itself primarily as *"fast, multi-backend file and
directory profiling"*. That is true, but it is **not the novelty** — `fd`,
`du`, `tree`, and Polars already cover that ground individually. The novelty
that no other library packages together is:

> **Dataset CI for ML — go from a folder to a verified, deduplicated,
> profiled dataset, and then *talk to it*, in one pipeline.**

This is the hook the roadmap is built around. Every other improvement
(API ergonomics, docs, agentic features, SOLID refactors) serves this story.

### Why "Dataset CI for ML" is the right framing

- **It names a job-to-be-done** that newcomers already have ("my dataset is
  a mess, is it safe to train on?"). "File profiling" does not.
- **It absorbs every existing capability** under one umbrella: scanning,
  enrichment, integrity/manifest checks, dedup, class-balance audits, the
  HTML audit report, and Filaraki's natural-language interface.
- **It positions the agentic layer as load-bearing**, not decorative — the
  agent is the *interface* to the CI pipeline, the way `gh` is to GitHub.
- **It is differentiated**. There is no widely-adopted equivalent in the
  Python data-prep ecosystem.

### Personas (all three are first-class)

| Persona              | Pain                                       | Filoma's promise                                                      |
| -------------------- | ------------------------------------------ | --------------------------------------------------------------------- |
| **ML engineer**      | "Is this dataset safe to train on?"        | One-line audit + HTML report + dedup + leakage check.                 |
| **Data engineer**    | "What's actually in this 2 TB folder?"     | Rust-fast scan → enriched dataframe → quick aggregations.             |
| **Researcher**       | "I just want to ask my filesystem things." | `filoma filaraki chat` → local LLM via Ollama, no API keys, no setup. |

The roadmap items below are tagged **[ML] / [DE] / [R]** where they are
persona-specific; untagged items help everyone.

---

## 2. SOLID principles audit

The codebase is in good shape, but a few seams will get strained as the
"Dataset CI" story grows. These are the concrete findings, scoped to the
files that exist today.

### 2.1 Tool registry duplication — **DRY / OCP violation** (highest leverage)

- `src/filoma/filaraki/tools.py` (~2025 LOC) and `src/filoma/mcp_server.py`
  (~997 LOC) each expose roughly the same set of "filesystem tools" but
  through independent registrations.
- Adding a new capability today requires editing **both** files. That makes
  the system closed to extension and open to drift between the two
  surfaces.
- **Fix (Phase 2):** introduce a single `ToolRegistry` (`@filoma.tool`
  decorator) that both Filaraki and the MCP server consume. Each tool
  becomes a small object with a `name`, `description`, `schema`, and a pure
  callable — the agent and the MCP server are then *adapters* over the
  same registry.

### 2.2 `Dataset` orchestrator — **SRP drift**

- `src/filoma/dataset.py` is small today (87 LOC) but already orchestrates
  snapshot, profiling, integrity, dedup, dataframe materialization, and
  agent acquisition.
- As we add CI-style stages (validate → audit → report → publish), this
  class will become a god-object.
- **Concrete hot path that proves the point:** running the headline chain
  `Pipeline(p).scan().enrich().verify().report()` walks the directory tree
  **~5 times**. `enrich()` builds a Polars dataframe (1 walk), `verify()`
  re-snapshots to compare (1 walk, unavoidable), and then `report()`
  delegates to `audit_dataset` whose three sub-tools
  (`audit_corrupted_files`, `generate_hygiene_report`,
  `assess_migration_readiness`) each probe the tree independently and a
  fourth internal `probe_to_df` rebuilds the same dataframe `enrich()`
  already cached. On a 44 k-item tree this is ~3 s of redundant scanning
  per audit — the single biggest speedup on the table.
- **Fix (Phase 3):** factor into a `Pipeline` of single-purpose stages
  (`Scan`, `Enrich`, `Verify`, `Dedup`, `Report`) that each implement a
  small `Stage` protocol. `Dataset` becomes a façade that composes the
  default stages — the LSP-friendly version of what we have now. Critical
  side benefit: stages share state (the enriched dataframe, the in-memory
  snapshot) so `Report` consumes what `Enrich` produced instead of
  re-walking the filesystem. We should also consider further caching of
  the enriched dataframe on disk (e.g. `dataset.pq`) so that subsequent
  runs are faster, but that's a separate design question.

### 2.3 `cli.py` (907 LOC) — **SRP, ISP**

- One module owns Typer commands for scanning, dedup, MCP, Filaraki, and
  more. Newcomers reading the CLI source to learn the library hit a wall.
- **Fix (Phase 2, low risk):** split into `cli/` package with one module
  per command group; the top-level `cli` Typer app simply mounts them.

### 2.4 Backend selection — **DIP, already good, keep it that way**

- The Rust → `fd` → Python fallback is the model citizen of the codebase:
  callers depend on a `Probe`/`Scanner` abstraction, not on a backend.
- **Action:** document this pattern in `docs/reference/architecture.md` as
  the *canonical* extension point, so future contributors copy it instead
  of inventing new ones.

### 2.5 Lazy imports — **keep, formalize**

- `import filoma` is intentionally cheap. This needs to stay true as we
  add agentic features (pydantic-ai, MCP, optional cloud providers).
- **Action (Phase 1):** add a single regression test that imports `filoma`
  and asserts none of `pydantic_ai`, `mcp`, `mistralai`, `google.*` are in
  `sys.modules` afterwards.

---

## 3. Phased roadmap

### Phase 0 — *Quick wins, ship now* (S, in this PR)

- [x] **Lead with the novelty hook in `README.md`.** One sentence at the
      top: "Dataset CI for ML — folder → verified dataset → insights →
      agent, in one pipeline."
- [x] **Link this roadmap from the docs nav** so contributors and curious
      users can see where the project is going.

### Phase 1 — *First-impression cohesion* (M)  **[all personas]**

Goal: a newcomer goes from `pip install filoma` to a working agentic audit
in under 60 seconds, with no decisions to make.

- [x] **`filoma demo` CLI command.** Downloads (or ships) a tiny sample
      dataset, runs `probe → enrich → verify → dedup → HTML report`, and
      opens the report. One command, no flags.
- [x] **Top-level `flm.ask("…")`** convenience that auto-instantiates a
      Filaraki agent against the current working directory. Zero ceremony
      for the "talk to your filesystem" pitch.
- [x] **Pipeline-as-object** — `flm.Pipeline(path).scan().enrich().verify().report()`
      fluent builder. The README's headline example becomes one line.
      (`Pipeline` is currently a fluent alias of `Dataset`; the proper
      stage-protocol refactor lands in Phase 3.)
- [x] **Lazy-import regression test** (see §2.5).

### Phase 2 — *SOLID consolidation* (L)  **[contributors / maintainers]**

Goal: make the codebase boring to extend. Every new agentic capability
should require editing exactly one file.

- [ ] **Single `ToolRegistry`.** Define `@filoma.tool` decorator with
      `name`, `description`, JSON schema (derived from type hints).
      Migrate `filaraki/tools.py` and `mcp_server.py` to consume it.
      Net result: one place to add tools, two adapters auto-update.
- [ ] **Split `cli.py` into `cli/` package** by command group.
- [ ] **Stage-based `Pipeline`** (see §2.2). `Dataset` becomes a façade.
- [ ] **Document the backend-selection pattern** as the canonical
      extension point in `docs/reference/architecture.md`.
- [ ] **Drift guard for bundled skills.** Add a `check-skills` task
      (poe / Make) that greps each `src/filoma/skills/*/SKILL.md` for
      the CLI commands and Python helpers it references and asserts
      they exist. Cleanest once the `ToolRegistry` lands so missing
      references fail via a single registry lookup. Ref §2.1.

### Phase 3 — *Dataset CI as a product* (L)  **[ML]**

Goal: deliver on the headline. Dataset CI should be runnable from the CLI,
from CI/CD, and from a notebook.

- [ ] **`filoma audit <path>`** as a first-class subcommand (today it's
      reachable, but buried under Filaraki). Exit code reflects pass/fail
      so it can be wired into GitHub Actions.
- [ ] **`filoma-action`** GitHub Action wrapping `filoma audit` with a
      sensible default report, posted as a PR comment for ML repos.
- [ ] **Versioned manifest format** (`filoma.lock` or similar) so two
      audits can be diffed: "what changed in my dataset since last
      training run?".
- [ ] **Quality gates as policies**: a small YAML that lets users say
      "fail if duplicate ratio > 1%, fail if any class < 50 samples",
      consumed by `filoma audit`.

### Phase 4 — *Documentation as the funnel* (M)

Docs are the second-best adoption lever after the README. Today they are
comprehensive but oriented around features, not jobs.

- [ ] **Restructure docs around the four jobs**: *audit*, *explore*,
      *dedup*, *talk*. Each gets a single-page tutorial that reads like a
      story, not a feature list.
- [ ] **Persona-tagged quickstarts** (ML / data eng / researcher) — three
      copies of the quickstart, each one optimized for that persona's
      first 5 minutes.
- [ ] **"Why filoma over X?"** comparison page (vs. `fd`, `du`, raw
      Polars, `pandas-profiling`, `great_expectations`). Currently
      missing — newcomers ask this question silently and bounce.
- [ ] **Roadmap visible from docs index** so contributors see the
      direction.

### Phase 5 — *Agentic depth* (XL, **future work, design only here**)

These are explicitly *not* implemented as part of this roadmap. They are
listed so design discussion has somewhere to live.

- [ ] **RAG over the dataset itself.** Ingest text/markdown/json files
      from a scanned tree into a local vector store (sqlite-vss or
      similar) so Filaraki can answer content questions, not just
      metadata questions. Local-first, no cloud dependency.
- [ ] **Schema-proposing agent.** Given a folder of CSV/Parquet/images,
      have the agent propose a dataset schema, a `Pipeline` config, and
      quality-gate policies — the user reviews and accepts.
- [ ] **Auto-generated cleanup scripts.** When the agent identifies
      duplicates / leakage / class imbalance, it offers a reviewable
      script (move/delete/rebalance) rather than executing destructively.
- [ ] **Proactive watch mode.** `filoma watch <path>` that surfaces
      drift between snapshots and notifies the user (or fails CI) when
      a quality gate trips.
- [ ] **Tool-marketplace style plugin discovery** — third-party packages
      register tools via the `ToolRegistry` from Phase 2, and Filaraki
      / MCP pick them up automatically.

### Phase 6 — *Distribution & community* (M, runs in parallel)

- [x] **Bundled agent skills.** Ship `filoma skills install` plus
      `SKILL.md` bundles (`filoma-dataset-ci`, `filoma-dedup`,
      `filoma-explore`) that drop into Claude Code, Claude Desktop, or
      VS Code chat. Generators for `AGENTS.md` (`filoma skills
      agents-md`) and Cursor rules (`filoma skills cursor-rules`)
      cover the rest of the agent ecosystem. See
      `src/filoma/skills/`.
- [ ] **One-line installer** already exists for nanobot+Ollama; promote
      it to a top-of-README install option for the agentic flow.
- [ ] **A dedicated `examples/` notebook per persona** (ML audit, data
      eng exploration, researcher chat) — each runnable end-to-end on a
      tiny sample dataset shipped with the repo.
- [ ] **Upstream `filoma-dataset-ci` to [anthropics/skills](https://github.com/anthropics/skills).**
      Pure marketing PR — surfaces filoma to anyone browsing
      Anthropic's open-source skills repo. No code change.
- [ ] **List the MCP server in [awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers).**
      Add filoma under the "data / files" category. One-line PR.
- [ ] **Show up where the personas already are**: a short post on a
      relevant ML/data-eng community, focused on the "Dataset CI for ML"
      hook (not on benchmarks).

---

## 4. Non-goals

To keep the project focused, the roadmap **does not** include:

- Becoming a general-purpose data-quality framework (that's
  `great_expectations` / `pandera`'s job).
- Replacing Polars or pandas as a dataframe library.
- A hosted/SaaS offering. Local-first is the differentiator.
- A bespoke LLM. Filaraki is, and stays, an interface over
  pluggable providers.

---

## 5. How to use this document

- Phase 0 is shipped together with this doc. Phases 1–4 are the
  near-term roadmap. Phase 5 is design-space only — open an issue
  before writing code.
- Each phase item should become a GitHub issue with persona tag,
  effort estimate, and a link back to the relevant section here.
- This is a living document. PRs that add or reorder items are
  welcome, as long as they keep the **"Dataset CI for ML"** framing
  as the north star.
