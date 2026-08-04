// header-widgets.ts — stopwatch and end-session controls in the HMI header.
// Recreated from the lost inline script (issue #59, Phase 0); split into
// proper modules during Phase 3.

import { stopSession } from '../api/client';
import { openAndGenerate, waitClose } from './debrief';
import { getSessionId } from './ptt';

document.addEventListener('DOMContentLoaded', () => {
  // --- Stopwatch ---
  let swSeconds = 0;
  let swTimer: ReturnType<typeof setInterval> | null = null;
  const swDisplay = document.getElementById('sw-display');
  const swWidget = document.getElementById('stopwatch-widget');
  const swToggle = document.getElementById('sw-toggle');
  const swReset = document.getElementById('sw-reset');
  if (!swDisplay || !swWidget || !swToggle || !swReset) return;
  const swDot = swWidget.querySelector('.sw-dot');

  function swRender(): void {
    const m = String(Math.floor(swSeconds / 60)).padStart(2, '0');
    const s = String(swSeconds % 60).padStart(2, '0');
    swDisplay!.textContent = m + ':' + s;
  }

  swToggle.addEventListener('click', () => {
    if (swTimer) {
      clearInterval(swTimer);
      swTimer = null;
      swWidget.classList.remove('sw-active');
      swDot?.classList.remove('sw-running');
      swToggle.innerHTML = '&#9654;';
    } else {
      swTimer = setInterval(() => {
        swSeconds++;
        swRender();
      }, 1000);
      swWidget.classList.add('sw-active');
      swDot?.classList.add('sw-running');
      swToggle.innerHTML = '&#10074;&#10074;';
    }
  });

  swReset.addEventListener('click', () => {
    swSeconds = 0;
    swRender();
  });

  // --- End session: stop backend session, then instructor debrief ---
  const endBtn = document.getElementById('end-session-btn') as HTMLButtonElement | null;
  if (!endBtn) return;
  endBtn.addEventListener('click', () => {
    endBtn.disabled = true;
    stopSession()
      .catch(() => {
        /* stop is best-effort */
      })
      .then(() => {
        const icao = document.getElementById('airport-badge')?.textContent?.trim() ?? '';
        return openAndGenerate(getSessionId(), icao === '----' ? '' : icao);
      })
      .then(() => waitClose())
      .then(() => {
        window.location.href = '/setup';
      })
      .catch(() => {
        endBtn.disabled = false;
      });
  });
});
