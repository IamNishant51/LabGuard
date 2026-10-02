# OpenCode workflow prompts

Use `AGENTS.md` as the primary instruction file.

## Start prompt
Read AGENTS.md and all docs in docs/. Inspect the repository and environment. Do not implement features yet. Report current state, assumptions to confirm, proposed folder structure, conflicts, and a Milestone 1 plan.

## Implement a milestone
Implement only Milestone N from docs/IMPLEMENTATION_PLAN.md. Follow AGENTS.md and relevant specs. First state plan and expected files. Implement one coherent slice, add tests, run relevant checks, fix failures, and report exact commands/results and remaining gaps. Never claim unverified success.

## Senior review
Review the current diff against docs/. Prioritize security, authorization, data correctness, performance, accessibility, and maintainability. Report findings by severity with file/line references. Fix confirmed issues and add regression tests without rewriting unrelated code.

## UI review
Review against docs/UI_UX.md at 1440px, 1024px, and 390px. Check populated/loading/empty/error states, keyboard navigation, contrast, responsive tables, and API-backed data. Remove generic decoration and dead controls. Run lint, typecheck, tests, and build.
