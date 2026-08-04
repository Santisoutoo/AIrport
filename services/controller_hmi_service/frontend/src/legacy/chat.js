// chat.js -- Receive-only WebSocket client for the controller chat panel.
//
// The backend (api/chat.py) subscribes to the Redis `hmi:chat` Pub/Sub
// channel and fans every payload out over this WebSocket. Payload shape
// (shared/services/taxi_router/hmi_chat.py):
//   { ts, session_id, sender: "pilot", callsign, registration, kind, text }
// Anything sent by the client is discarded server-side, so this module
// only listens and renders each line through Ptt.addAgentMessage().

import { Ptt } from './ptt.js';

(function () {
    'use strict';

    var RECONNECT_MIN_MS = 1000;
    var RECONNECT_MAX_MS = 15000;

    var _reconnectMs = RECONNECT_MIN_MS;

    function _wsUrl() {
        var proto = location.protocol === 'https:' ? 'wss' : 'ws';
        return proto + '://' + location.host + '/api/v1/plugin/chat/stream';
    }

    function _onMessage(event) {
        var payload;
        try {
            payload = JSON.parse(event.data);
        } catch (_) {
            return; // ignore malformed payloads
        }
        if (!payload || typeof payload.text !== 'string' || !payload.text) return;

        var callsign = payload.callsign || payload.sender || 'PILOT';
        Ptt.addAgentMessage(String(callsign), payload.text);
    }

    function _connect() {
        var ws;
        try {
            ws = new WebSocket(_wsUrl());
        } catch (_) {
            _scheduleReconnect();
            return;
        }

        ws.onopen = function () {
            _reconnectMs = RECONNECT_MIN_MS;
        };
        ws.onmessage = _onMessage;
        ws.onclose = _scheduleReconnect;
        ws.onerror = function () {
            ws.close();
        };
    }

    function _scheduleReconnect() {
        setTimeout(_connect, _reconnectMs);
        _reconnectMs = Math.min(_reconnectMs * 2, RECONNECT_MAX_MS);
    }

    document.addEventListener('DOMContentLoaded', _connect);
})();
