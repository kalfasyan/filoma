## Plan: Filoma Brain Phase 2 (Advanced Agentic Capabilities)

Deliver advanced agentic features through a reliability-first rollout: stabilize the current Brain first, then add deterministic multi-step workflow tools, then optional advanced stats, then lifecycle recommendations. This keeps scope realistic, preserves compatibility, and gives measurable quality gates.

**Steps**
1. Phase 0: Baseline and scope guardrails  
Define KPI targets and explicit non-destructive boundaries (recommendation-only behavior). Confirm Phase 2 excludes autonomous file mutation.

2. Phase 1: Reliability foundation (blocks all later phases)  
Add structured telemetry for tool calls and create deterministic regression/eval coverage for existing Brain workflows (search, dataframe chaining, integrity, quality). Expand tests beyond init/import smoke checks.

3. Phase 2: Deterministic workflow orchestration (depends on 2)  
Implement high-level orchestrator tools for:
- Corrupted file audit
- Dataset hygiene report
- Migration readiness report  
All outputs must be typed/structured with status, evidence, confidence, and recommended actions.

4. Phase 3: Lightweight statistical intelligence (depends on 3)  
Add core statistical detection without heavy dependencies first (z-score/MAD outliers, imbalance metrics, numeric correlation where available). Expose this through one stable entrypoint to reduce prompt/tool fragility.

5. Phase 4: Optional advanced stats extras (parallel with 6 after interfaces stabilize)  
Add optional scipy/scikit-learn extras with lazy imports and fallback to Phase 3 methods when unavailable.

6. Phase 5: Lifecycle intelligence v1 (depends on 3; parallel with 5 where independent)  
Add deterministic health scoring, snapshot policy recommendations, and rule-based compliance validation using existing integrity/quality/dedup signals.

7. Phase 6: Documentation and UX alignment (parallel with 4-6)  
Update guides and examples to reflect new workflows, safety boundaries, optional feature availability, and troubleshooting.

8. Phase 7: Release hardening (depends on 4-7)  
Run full verification matrix, benchmark latency, finalize release notes, and publish rollout guidance.

**Parallelization and Dependencies**
1. Sequential critical path: Phase 1 -> Phase 2 -> Phase 3.  
2. Parallelizable after Phase 2 interfaces settle:
- Phase 4 (optional advanced stats)
- Phase 5 (lifecycle intelligence)
- Phase 6 (docs/UX updates)  
3. Phase 7 starts only after all in-scope phases complete.

**Relevant files**
- [src/filoma/brain/agent.py](src/filoma/brain/agent.py)  
Register orchestrator tools and refine prompt behavior for deterministic chaining.

- [src/filoma/brain/tools.py](src/filoma/brain/tools.py)  
Implement workflow, statistical, and lifecycle tools with structured responses.

- [src/filoma/dataset.py](src/filoma/dataset.py)  
Reuse dataset lifecycle orchestration points for report generation inputs.

- [src/filoma/core/verifier.py](src/filoma/core/verifier.py)  
Reuse integrity/quality signals for lifecycle recommendations.

- [pyproject.toml](pyproject.toml)  
Add optional advanced statistics dependency group(s) and keep core install lean.

- [tests/test_brain_poc_init.py](tests/test_brain_poc_init.py)  
Preserve smoke coverage and strengthen Brain initialization/registration assertions.

- [docs/guides/brain.md](docs/guides/brain.md)  
Add advanced workflow docs and expected output conventions.

- [README.md](README.md)  
Update high-level feature narrative and realistic workflow examples.

**Verification**
1. Unit tests  
Validate input handling, schema-valid outputs, and fallback behavior when optional deps are absent.

2. Integration tests  
Verify multi-step tool chaining and state continuity across a single chat session.

3. E2E evals  
Run golden prompts to verify tool sequencing, output faithfulness, and non-hallucinated summaries.

4. Performance checks  
Track p50/p95 latency on representative small and medium fixtures.

5. Manual QA  
Run 3 reference workflows in CLI chat: corruption audit, hygiene report, migration readiness.

**Acceptance Criteria**
1. Existing Brain workflows remain backward compatible.  
2. New workflow tools produce schema-valid outputs in all tests.  
3. Golden eval pass rate is at least 95% on the supported model matrix.  
4. Optional advanced stats do not impact base installation behavior.  
5. Docs contain at least 3 realistic end-to-end advanced workflow examples.

**Decisions**
- Included: deterministic orchestration, explainable recommendations, instrumentation, optional advanced analytics.
- Excluded for Phase 2: autonomous file mutation, distributed agent execution, GUI/dashboard work, model fine-tuning.
- Operating assumption: Brain remains read-only except explicit export behavior.
