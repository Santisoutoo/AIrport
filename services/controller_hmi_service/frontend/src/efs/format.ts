// Pure formatting helpers for flight strips and SMR labels.

/** ICAO-style level: F<hundreds> at/above 10000 ft, A<hundreds> below. */
export function formatFL(feet: number | undefined): string {
  if (!feet) return '----';
  if (feet >= 10000) return 'F' + Math.round(feet / 100);
  return 'A' + String(Math.round(feet / 100)).padStart(3, '0');
}

/** N-prefixed 4-digit speed (e.g. N0460). */
export function formatSpeed(knots: number | undefined): string {
  if (!knots) return '-----';
  return 'N' + String(knots).padStart(4, '0');
}

/** hhmm number → "hh:mm". */
export function formatTime(hhmm: number | undefined): string {
  if (!hhmm && hhmm !== 0) return '--:--';
  const s = String(Math.floor(hhmm)).padStart(4, '0');
  return s.slice(0, 2) + ':' + s.slice(2, 4);
}

/** Deterministic hash-based squawk from a registration (digits 0-7 only). */
export function generateSquawk(reg: string): string {
  let hash = 0;
  for (let i = 0; i < reg.length; i++) {
    hash = (hash << 5) - hash + reg.charCodeAt(i);
    hash |= 0;
  }
  const code = (Math.abs(hash) % 7000) + 1000;
  const str = String(code);
  let result = '';
  for (let j = 0; j < 4; j++) {
    const d = parseInt(str[j] ?? '0') || 0;
    result += Math.min(d, 7);
  }
  return result;
}

export function truncateRoute(route: string | undefined, maxLen: number): string {
  if (!route) return 'DCT';
  if (route.length <= maxLen) return route;
  return route.substring(0, maxLen) + '...';
}
