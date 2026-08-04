// chat.ts — receive-only WebSocket client for the controller chat panel.
//
// The backend (api/chat.py) subscribes to the Redis `hmi:chat` Pub/Sub
// channel and fans every payload out over this WebSocket. Payload shape
// (shared/services/taxi_router/hmi_chat.py):
//   { ts, session_id, sender: "pilot", callsign, registration, kind, text }
// Anything sent by the client is discarded server-side, so this module
// only listens and renders each line through Ptt.addAgentMessage().

import type { ChatPayload } from '../types/api';
import { Ptt } from './ptt';

const RECONNECT_MIN_MS = 1000;
const RECONNECT_MAX_MS = 15000;

let _reconnectMs = RECONNECT_MIN_MS;

function _wsUrl(): string {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return proto + '://' + location.host + '/api/v1/plugin/chat/stream';
}

function _onMessage(event: MessageEvent): void {
  let payload: ChatPayload;
  try {
    payload = JSON.parse(String(event.data)) as ChatPayload;
  } catch {
    return; // ignore malformed payloads
  }
  if (!payload || typeof payload.text !== 'string' || !payload.text) return;

  const callsign = payload.callsign || payload.sender || 'PILOT';
  Ptt.addAgentMessage(String(callsign), payload.text);
}

function _connect(): void {
  let ws: WebSocket;
  try {
    ws = new WebSocket(_wsUrl());
  } catch {
    _scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    _reconnectMs = RECONNECT_MIN_MS;
  };
  ws.onmessage = _onMessage;
  ws.onclose = _scheduleReconnect;
  ws.onerror = () => {
    ws.close();
  };
}

function _scheduleReconnect(): void {
  setTimeout(_connect, _reconnectMs);
  _reconnectMs = Math.min(_reconnectMs * 2, RECONNECT_MAX_MS);
}

document.addEventListener('DOMContentLoaded', _connect);
