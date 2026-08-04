// Data-ownership module: the five polling loops and the app-level state
// they feed (flight plans, live positions, current airport). After the
// Phase-3 split this is the closest thing the HMI has to a store — see
// docs/adr-001-no-global-state-library.md.

import { getAircraftPositions, getAirport, getStrips, getTaf, getWeather } from './api/client';
import { loadStripStates, renderFlightStrips } from './legacy/efs';
import {
  renderTafModule,
  renderWeatherModule,
  setConnectionStatus,
  updateRefreshTimestamp,
} from './legacy/weather';
import { updateWindInstruments } from './legacy/wind';
import { checkRIMCAS } from './rimcas';
import { updateRunwaySequence } from './runway-sequence';
import { initSMRMap, setILSForArrivalRunway, updateSMRAircraft } from './smr/render';
import { smrState } from './smr/state';
import type { AircraftPosition, FlightPlan } from './types/api';

const STRIP_REFRESH_MS = 15000;
const WEATHER_REFRESH_MS = 60000;
const AIRPORT_REFRESH_MS = 30000;
const POSITIONS_REFRESH_MS = 1000; // live aircraft positions

export let flightPlans: FlightPlan[] = [];
export let currentICAO = '';

let livePositions: Record<string, AircraftPosition> = {};

export function getLivePositions(): Record<string, AircraftPosition> {
  return livePositions;
}

/** Start every refresh loop. Called once from the composition root. */
export function startPolling(): void {
  loadAirport();
  loadStripStates(() => {
    loadFlightStrips();
  });
  loadWeather();
  loadTaf();

  setInterval(loadAirport, AIRPORT_REFRESH_MS);
  setInterval(() => {
    loadStripStates(() => loadFlightStrips());
  }, STRIP_REFRESH_MS);
  setInterval(loadWeather, WEATHER_REFRESH_MS);
  setInterval(loadTaf, WEATHER_REFRESH_MS);

  // Live aircraft positions for the SMR map — faster cadence so dots track movement
  loadAircraftPositions();
  setInterval(loadAircraftPositions, POSITIONS_REFRESH_MS);
}

function loadAircraftPositions(): void {
  getAircraftPositions()
    .then((arr) => {
      const next: Record<string, AircraftPosition> = {};
      (arr || []).forEach((a) => {
        if (a && a.registration) next[a.registration] = a;
      });
      livePositions = next;
      updateSMRAircraft(flightPlans);
    })
    .catch(() => {
      /* ignore transient failures */
    });
}

function loadFlightStrips(): void {
  getStrips()
    .then((data) => {
      flightPlans = data;
      rerenderStrips();
      updateRefreshTimestamp();
      setConnectionStatus(true);
    })
    .catch((err: unknown) => {
      console.error('Failed to load strips:', err);
      setConnectionStatus(false);
    });
}

export function rerenderStrips(): void {
  renderFlightStrips(flightPlans);
  updateSMRAircraft(flightPlans);
  updateRunwaySequence(flightPlans);
  checkRIMCAS(flightPlans);
}

function loadWeather(): void {
  getWeather()
    .then((data) => {
      renderWeatherModule(data);
      updateWindInstruments(data);
    })
    .catch((err: unknown) => {
      console.error('Failed to load weather:', err);
    });
}

function loadAirport(): void {
  getAirport()
    .then((data) => {
      const icao = data.icao || '----';
      const badge = document.getElementById('airport-badge');
      if (badge) badge.textContent = icao;
      const smrLabel = document.getElementById('smr-airport');
      if (smrLabel) smrLabel.textContent = icao;

      // Reload map, weather & TAF when airport changes
      if (icao !== currentICAO && icao !== '----') {
        currentICAO = icao;
        smrState.activeILSRunway = null;
        initSMRMap();
        loadWeather();
        loadTaf();
      }
    })
    .catch((err: unknown) => {
      console.error('Failed to load airport:', err);
    });
}

function loadTaf(): void {
  getTaf()
    .then((data) => {
      // Handle various response structures from the weather service
      let rawTaf: string | null = null;
      if (typeof data === 'string') {
        rawTaf = data;
      } else if (data.raw_taf) {
        rawTaf = data.raw_taf;
      } else if (data.raw) {
        rawTaf = data.raw;
      } else if (data.taf) {
        rawTaf = data.taf;
      }
      renderTafModule(rawTaf);
    })
    .catch((err: unknown) => {
      console.error('Failed to load TAF:', err);
      renderTafModule('TAF unavailable');
    });
}

// Re-export for consumers that used to reach into app.ts for this.
export { setILSForArrivalRunway };
