# Architecture Decision Records

Short records of decisions that were actually evaluated, with the alternatives that were
rejected and the conditions under which the decision should be revisited. One numbered
sequence for the whole repo, regardless of where the file lives — frontend-scoped ADRs stay
next to the code they govern.

| # | Decision | Status | Location |
|---|---|---|---|
| 001 | No global state-management library (for now) — do not introduce Redux Toolkit in the controller HMI frontend | accepted | [`services/controller_hmi_service/frontend/docs/adr-001-no-global-state-library.md`](../../services/controller_hmi_service/frontend/docs/adr-001-no-global-state-library.md) |
| 002 | Stay on Python/FastAPI and modernize incrementally — do not rewrite the backend | accepted | [`adr-002-backend-stack.md`](adr-002-backend-stack.md) |

New ADRs take the next free number and the filename pattern `adr-NNN-<slug>.md`. Repo-wide
decisions go in this directory; keep the header block (`Status`, `Date`, `Context`) and the
`Context` / `Decision` / alternatives / revisit-triggers structure used by the existing ones.
