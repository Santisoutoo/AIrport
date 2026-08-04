# ADR-001: No global state-management library (for now)

- Status: accepted
- Date: 2026-08-04
- Context: epic #59 (controller HMI migration to TypeScript), Phase 4

## Context

The project rule (personal_projects `CLAUDE.md`) mandates **Redux Toolkit** whenever
global state management is introduced — never Zustand, Context API or plain Redux.
Phase 4 of epic #59 required an explicit evaluation of whether the migrated HMI
frontend should adopt it.

The app's state surface after the Phase 3 modularization:

- `src/polling.ts` owns the server-derived data (`flightPlans`, live positions,
  `currentICAO`) and the five refresh loops; consumers are direct function calls
  (`rerenderStrips()` fans out to strips, SMR, runway sequence, RIMCAS).
- `src/smr/state.ts` owns the SMR view state (graph, bounds, viewBox, ILS runway).
- `src/legacy/ptt.ts` owns the chat log and PTT state.
- Everything else is localStorage-backed settings behind `src/lib/storage.ts`.

## Decision

**Do not introduce Redux Toolkit (or any state library) at this time.**

Rationale:

- There is no React. RTK without React means hand-rolling `store.subscribe`
  plus per-consumer diffing; the boilerplate would exceed the entire current
  state surface.
- After Phase 3, `polling.ts` + `smr/state.ts` already centralize data ownership
  with typed access — they are the app's store, at near-zero cost.
- Renderers write straight to the DOM; there is no derived or cross-cutting
  state that multiple independent consumers select from.

## Revisit triggers

Adopt **Redux Toolkit** (`createSlice` / `configureStore`, RTK Query for server
state) — as mandated by the project rule — if any of these happen:

1. The HMI (or a panel of it) is rewritten in React.
2. More than two consumers need the same *derived* state (selectors/memoization
   would pay for themselves).
3. Undo/redo, time-travel or cross-tab state sync becomes a requirement.

Until then, new shared state should follow the existing pattern: a typed module
that owns its data and exposes functions, not a new library.
