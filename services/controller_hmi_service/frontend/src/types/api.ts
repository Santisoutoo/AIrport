// Typed mirror of the backend contract.
// Source of truth: services/controller_hmi_service/api/routes.py (HMI),
// api/plugin_routes.py + api/models.py (plugin), api/chat.py (WebSocket),
// shared/services/taxi_router/hmi_chat.py (chat payload).

// ---------------------------------------------------------------------------
// /api/v1/hmi
// ---------------------------------------------------------------------------

export interface Airport {
  icao: string;
}

/** Flight plan dict from the flight-plan service, merged with virtual
 * arrival strips (routes.py register_arrival_strip shows the full shape). */
export interface FlightPlan {
  aircraft_registration: string;
  callsign?: string;
  aircraft_type?: string;
  flight_rules?: string;
  flight_type?: string;
  wake_turbulence_category?: string;
  equipment?: string;
  transponder?: string;
  departure_ICAO?: string;
  departure_time?: number;
  cruising_speed?: number;
  cruising_altitude?: number;
  route?: string;
  destination_ICAO?: string;
  total_EET?: string;
  alternate_ICAO?: string;
  second_alternate_ICAO?: string;
  other_info?: string;
  endurance?: string;
  people_on_board?: string;
  remarks?: string;
  PIC_name?: string;
  squawk?: string | number;
  /** Only some producers set these; updateRunwaySequence checks them. */
  arrival_airport?: string;
}

export type StripColumn = 'PRE_TAXI' | 'TAXI' | 'RUNWAY' | 'ARRIVALS';

export interface StripState {
  phase: string;
  column: StripColumn;
}

export type StripStates = Record<string, StripState>;

export interface AircraftPosition {
  registration: string;
  callsign: string;
  latitude: number;
  longitude: number;
  heading: number;
  ground_speed: number;
  phase: string;
}

// Airport graph for the SMR map (data/scripts airport_graph_builder).
export interface GraphNode {
  lat: number;
  lon: number;
  name?: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  name?: string;
  category?: string;
}

export interface Stand {
  name: string;
  lat: number;
  lon: number;
  size_cats?: string[];
}

export interface RunwayEnd {
  designator: string;
  lat: number;
  lon: number;
}

export interface Runway {
  end1: RunwayEnd;
  end2: RunwayEnd;
}

export interface AirportGraph {
  nodes: Record<string, GraphNode>;
  edges: GraphEdge[];
  stands: Stand[];
  runways: Runway[];
}

// Weather service passthroughs.
export interface CloudLayer {
  coverage: string;
  base_ft: number;
}

export interface Metar {
  raw_metar?: string;
  flight_category?: string;
  qnh_hpa?: number;
  clouds?: CloudLayer[];
  visibility_m?: number;
  wind_direction?: number;
  wind_speed?: number;
  wind_gust?: number;
  weather?: string;
  temperature_c?: number;
  dewpoint_c?: number;
}

/** GET /taf returns either a raw string or an object with one of these keys
 * (app.js loadTaf handles all variants). */
export type TafResponse = string | { raw_taf?: string; raw?: string; taf?: string };

export interface AtisRequest {
  arrival_runway: string | null;
  departure_runway: string | null;
  approach: string | null;
  qfe: number | null;
  include_tl: boolean;
  include_ta: boolean;
  remarks: string | null;
  metar_station: string | null;
  preview: boolean;
}

export interface AtisResponse {
  atis_text?: string;
  atis_letter?: string;
  arrival_runway?: string;
  departure_runway?: string;
  icao_code?: string;
  transition_level?: string;
  transition_altitude?: number | string;
}

export interface TranscriptionResponse {
  text?: string;
}

export interface DispatchResponse {
  reply?: string;
  callsign?: string;
  aircraft_registration?: string;
  /** Which pilot agent answered (DEL / GND / TWR). */
  agent?: string;
}

export interface DebriefExample {
  ts?: string;
  quote?: string;
  note?: string;
  verdict?: string;
}

export interface DebriefCategory {
  name?: string;
  score?: number;
  summary?: string;
  examples?: DebriefExample[];
}

export interface DebriefReport {
  overall_score?: number;
  categories?: DebriefCategory[];
  strengths?: string[];
  improvements?: string[];
  instructor_summary?: string;
}

export interface DebriefResponse {
  too_short?: boolean;
  debrief?: DebriefReport;
}

// ---------------------------------------------------------------------------
// /api/v1/plugin
// ---------------------------------------------------------------------------

export interface AuthResponse {
  success: boolean;
  message?: string;
  username?: string;
}

export interface StartSessionRequest {
  session_type: string;
  weather: string;
  aircraft_count: number;
  complexity: string;
}

export interface StartSessionResponse {
  success: boolean;
  message?: string;
}

export interface SessionStatus {
  status?: string;
  icao?: string;
}

/** Payload fanned out on /api/v1/plugin/chat/stream
 * (shared/services/taxi_router/hmi_chat.py). */
export interface ChatPayload {
  ts?: number;
  session_id?: string;
  sender?: string;
  callsign?: string;
  registration?: string;
  kind?: string;
  text?: string;
}

// ---------------------------------------------------------------------------
// Runtime config (static/config.js, generated by main.py)
// ---------------------------------------------------------------------------

export interface HmiConfig {
  ASR_URL?: string;
  ASR_URL_LARGE?: string;
  ORCHESTRATOR_URL?: string;
}
