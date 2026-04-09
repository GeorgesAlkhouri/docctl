# PLANS

Planning workflow:
1. Capture active plan in `docs/exec-plans/active/`.
2. For every new feature plan, ask explicit acceptance-test questions before
   implementation and record the agreed scenarios in the active plan.
3. Define explicit acceptance checks per bounded validate loop.
4. Classify planned test coverage by scope to avoid overlap:
   - `tests/integration/` is the default for feature workflow behavior across
     module/service boundaries and contracts,
   - `tests/acceptance/` is only for a small set of top-level CLI/E2E smoke
     scenarios that prove releasability.
5. Move completed plans to `docs/exec-plans/completed/`.
6. Track leftovers in `docs/exec-plans/tech-debt-tracker.md`.

Related:
- [Active plans](exec-plans/active/README.md)
- [Completed plans](exec-plans/completed/README.md)
- [Debt tracker](exec-plans/tech-debt-tracker.md)
