// Typed fetch wrappers for every backend endpoint the HMI calls.
// All requests are same-origin: FastAPI proxies to the other services.

import type {
  Airport,
  AirportGraph,
  AircraftPosition,
  AtisRequest,
  AtisResponse,
  AuthResponse,
  DebriefResponse,
  DispatchResponse,
  FlightPlan,
  Metar,
  SessionStatus,
  StartSessionRequest,
  StartSessionResponse,
  StripState,
  StripStates,
  TafResponse,
  TranscriptionResponse,
} from '../types/api';

const HMI_BASE = '/api/v1/hmi';
const PLUGIN_BASE = '/api/v1/plugin';

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = 'ApiError';
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const body = (await resp.json()) as { detail?: string };
      if (body && typeof body.detail === 'string') detail = body.detail;
    } catch {
      // non-JSON error body — keep the HTTP status message
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

function postJson<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ---------------------------------------------------------------------------
// /api/v1/hmi
// ---------------------------------------------------------------------------

export const getAirport = () => request<Airport>(`${HMI_BASE}/airport`);

export const getStrips = () => request<FlightPlan[]>(`${HMI_BASE}/strips`);

export const getStripStates = () => request<StripStates>(`${HMI_BASE}/strips/states`);

export const patchStripState = (registration: string, phase: string) =>
  request<StripState>(`${HMI_BASE}/strips/${encodeURIComponent(registration)}/state`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ phase }),
  });

export const getAircraftPositions = () =>
  request<AircraftPosition[]>(`${HMI_BASE}/aircraft/positions`);

export const getAirportGraph = () => request<AirportGraph>(`${HMI_BASE}/airport/graph`);

export const getWeather = () => request<Metar>(`${HMI_BASE}/weather`);

export const getTaf = () => request<TafResponse>(`${HMI_BASE}/taf`);

export const getAtis = () => request<AtisResponse>(`${HMI_BASE}/atis`);

export const generateAtis = (body: Partial<AtisRequest>) =>
  postJson<AtisResponse>(`${HMI_BASE}/atis/generate`, body);

export const transcribe = (audio: Blob, filename: string, sessionId: string) => {
  const fd = new FormData();
  fd.append('audio', audio, filename);
  fd.append('session_id', sessionId);
  return request<TranscriptionResponse>(`${HMI_BASE}/asr/transcribe`, {
    method: 'POST',
    body: fd,
  });
};

export const dispatchOrchestrator = (sessionId: string, message: string) =>
  postJson<DispatchResponse>(`${HMI_BASE}/orchestrator/dispatch`, {
    session_id: sessionId,
    message,
  });

export const generateDebrief = (sessionId: string, airportIcao: string) =>
  postJson<DebriefResponse>(`${HMI_BASE}/debrief/generate`, {
    session_id: sessionId,
    airport_icao: airportIcao,
  });

// ---------------------------------------------------------------------------
// /api/v1/plugin
// ---------------------------------------------------------------------------

export const login = (username: string, password: string) =>
  postJson<AuthResponse>(`${PLUGIN_BASE}/login`, { username, password });

export const register = (username: string, password: string) =>
  postJson<AuthResponse>(`${PLUGIN_BASE}/register`, { username, password });

export const startSession = (body: StartSessionRequest) =>
  postJson<StartSessionResponse>(`${PLUGIN_BASE}/session/start`, body);

export const stopSession = () =>
  request<unknown>(`${PLUGIN_BASE}/session/stop`, { method: 'POST' });

export const getSessionStatus = () => request<SessionStatus>(`${PLUGIN_BASE}/session/status`);
