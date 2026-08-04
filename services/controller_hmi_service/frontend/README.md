# Controller HMI frontend

Vite + TypeScript source for the controller HMI (`index.html` TWR workstation,
`setup.html` login/session screens). Built output lands in `../static/`, which
FastAPI (`main.py`) serves at `/` — `static/` is **generated, never edited or
committed**.

## Layout

```
frontend/
  index.html, setup.html   Vite entry pages (DOM contract lives here)
  public/config.js         dev fallback; in prod main.py regenerates static/config.js
  src/main.ts              entry for index.html (styles + legacy modules)
  src/setup-main.ts        entry for setup.html
  src/legacy/*.js          pre-migration vanilla JS (epic #59 converts to TS)
  src/styles/*.css         stylesheets, imported from the entries
```

`config.js` is intentionally outside the bundle graph: both pages load it with
a plain `<script src="/config.js">` because `main.py` rewrites it at every
service start from `ASR_URL` / `ORCHESTRATOR_URL`.

## Commands

| Command             | What it does                                             |
| ------------------- | -------------------------------------------------------- |
| `npm run dev`       | Dev server on :5173, proxies `/api` (incl. WS) to :8005  |
| `npm run build`     | Typecheck + production build into `../static/`           |
| `npm run watch`     | Rebuild into `../static/` on every change                |
| `npm run typecheck` | `tsc --noEmit`                                           |
| `npm run lint`      | ESLint over `src/`                                       |
| `npm run format`    | Prettier                                                 |

## Dev workflows with docker compose

`docker-compose.yml` bind-mounts `./static:/app/static`, so the host copy of
`static/` **shadows** whatever the Docker image built. Pick one:

1. **Simplest** — build once, then run the stack:

   ```bash
   cd services/controller_hmi_service/frontend
   npm ci && npm run build
   docker compose up -d
   ```

2. **Frontend iteration against the full stack** — keep a watcher running;
   every save rebuilds into the bind-mounted `static/` (reload the browser):

   ```bash
   npm run watch
   ```

3. **Fastest loop** — Vite dev server with API proxy (no rebuild per save,
   HMR for CSS): run the stack, then

   ```bash
   npm run dev   # open http://localhost:5173
   ```

Without the compose bind mount (e.g. Cloud Run), the image is self-contained:
the Dockerfile's first stage runs `npm run build` and copies `static/` in.
