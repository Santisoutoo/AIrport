// Dev-only fallback for `vite dev` / fresh builds.
// In production main.py overwrites static/config.js at every service start
// from the ASR_URL / ORCHESTRATOR_URL env vars — do not put real values here.
window.HMI_CONFIG = {
  ASR_URL: "http://localhost:8006/api/v1/asr",
  ORCHESTRATOR_URL: "http://localhost:8007"
};
