# AIrport — Project Instructions

## State Management

Always use **Redux Toolkit (RTK)** for all state management.  
- Use `createSlice`, `createAsyncThunk`, and `configureStore` from `@reduxjs/toolkit`.  
- Never introduce plain Redux, Zustand, Context API (for global state), or any other state library.  
- RTK Query is preferred for server state / API calls.

## Documentation (openwiki)

This repo has agent-facing documentation under [`openwiki/`](openwiki/) — structured markdown
optimized for finding repo context fast (architecture, services, agents, shared, X-Plane,
testing). **Consult [`openwiki/index.md`](openwiki/index.md) first** when you need to understand
how the codebase fits together. Human-facing docs live in [`docs/`](docs/).

Refresh the wiki with the `/update-docs` command (runs the `openwiki-writer` agent on Claude
Sonnet). It updates incrementally from git changes; see
[`.claude/agents/openwiki-writer.md`](.claude/agents/openwiki-writer.md).
