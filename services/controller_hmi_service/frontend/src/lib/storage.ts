// Typed accessors for every localStorage key the HMI uses.
// All reads are defensive: malformed JSON falls back to the default.

export interface AsrSettings {
  ptt_key?: string;
  input_device?: string;
  output_device?: string;
  backend?: string;
  ollama_url?: string;
  ollama_model?: string;
  api_key?: string;
  api_base_url?: string;
  api_model?: string;
}

export interface PanelSizes {
  leftW: number;
  dashH: number;
  bottomH: number;
  commsH: number;
}

export interface LabelOffset {
  ox: number;
  oy: number;
}

function readJson<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // storage full / unavailable — settings are best-effort
  }
}

// ---- airport_asr_settings ----

export const getAsrSettings = (): AsrSettings => readJson<AsrSettings>('airport_asr_settings') ?? {};

export const setAsrSettings = (settings: AsrSettings): void =>
  writeJson('airport_asr_settings', settings);

// ---- airport_username ----

export const getUsername = (): string | null => localStorage.getItem('airport_username');

export const setUsername = (username: string): void =>
  localStorage.setItem('airport_username', username);

// ---- hmi-panel-sizes ----

export function getPanelSizes(): PanelSizes | null {
  const p = readJson<PanelSizes>('hmi-panel-sizes');
  if (
    p &&
    (['leftW', 'dashH', 'bottomH', 'commsH'] as const).every(
      (k) => typeof p[k] === 'number' && isFinite(p[k]),
    )
  ) {
    return p;
  }
  return null;
}

export const setPanelSizes = (sizes: PanelSizes): void => writeJson('hmi-panel-sizes', sizes);

// ---- smr_lbl_offset_{registration} ----

export const getSmrLabelOffset = (registration: string): LabelOffset =>
  readJson<LabelOffset>(`smr_lbl_offset_${registration}`) ?? { ox: 0, oy: 0 };

export const setSmrLabelOffset = (registration: string, offset: LabelOffset): void =>
  writeJson(`smr_lbl_offset_${registration}`, offset);

// ---- strip_lbl_{registration}_{key} ----

export const getStripLabel = (registration: string, key: string): string | null =>
  localStorage.getItem(`strip_lbl_${registration}_${key}`);

export const setStripLabel = (registration: string, key: string, value: string): void =>
  localStorage.setItem(`strip_lbl_${registration}_${key}`, value);
