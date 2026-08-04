// Lighting panel: PAPI slider, stopbar/runway/approach toggles, LVP.

export function initLightingControls(): void {
  // PAPI slider
  const papiSlider = document.getElementById('papi-slider') as HTMLInputElement | null;
  const papiValue = document.getElementById('papi-value');
  if (papiSlider && papiValue) {
    papiSlider.addEventListener('input', () => {
      papiValue.textContent = papiSlider.value;
    });
  }

  // Toggle buttons
  initToggleButton('stopbar-btn');
  initToggleButton('rwy-lights-btn');
  initToggleButton('approach-lights-btn');

  // LVP toggle
  const lvp = document.getElementById('lvp-indicator');
  if (lvp) {
    lvp.addEventListener('click', () => {
      lvp.classList.toggle('lvp-on');
      lvp.classList.toggle('lvp-off');
    });
  }
}

function initToggleButton(id: string): void {
  const btn = document.getElementById(id);
  if (!btn) return;

  btn.addEventListener('click', () => {
    const isOn = btn.classList.contains('stopbar-on');
    if (isOn) {
      btn.classList.remove('stopbar-on');
      btn.classList.add('stopbar-off');
      btn.textContent = 'OFF';
    } else {
      btn.classList.remove('stopbar-off');
      btn.classList.add('stopbar-on');
      btn.textContent = 'ON';
    }
  });
}
