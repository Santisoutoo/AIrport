// Composition root for index.html (TWR workstation).
// Side-effect imports wire each panel's own listeners; the explicit init
// below starts the clock, widgets, SMR map and polling loops.

import './styles/efs.css';
import './styles/debrief.css';

import './legacy/resize';
import './legacy/atis';
import './legacy/debrief';
import './legacy/ptt';
import './legacy/chat';
import './legacy/header-widgets';

import { initWindInstruments } from './legacy/wind';
import { startUTCClock } from './legacy/weather';
import { initLightingControls } from './lighting';
import { startPolling } from './polling';
import { initSMRMap } from './smr/render';

document.addEventListener('DOMContentLoaded', () => {
  startUTCClock();
  initWindInstruments();
  initLightingControls();
  initSMRMap();
  startPolling();
});
