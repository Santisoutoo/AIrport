// Pure wind-component math for the runway wind widget.

export interface WindComponents {
  /** Signed headwind (negative = tailwind), as displayed component. */
  headwind: number;
  /** Absolute crosswind component. */
  crosswind: number;
  /** Tailwind (0 when headwind). */
  tailwind: number;
  /** Headwind clamped to 0 for display. */
  hwDisplay: number;
}

/** Decompose wind (direction °, speed kt) onto a runway heading. */
export function computeWindComponents(
  windDirectionDeg: number,
  windSpeedKt: number,
  runwayHeadingDeg: number,
): WindComponents {
  const angleDiff = ((windDirectionDeg - runwayHeadingDeg) * Math.PI) / 180;
  const headwind = Math.round(windSpeedKt * Math.cos(angleDiff));
  const crosswind = Math.round(Math.abs(windSpeedKt * Math.sin(angleDiff)));
  const tailwind = headwind < 0 ? Math.abs(headwind) : 0;
  const hwDisplay = headwind >= 0 ? headwind : 0;
  return { headwind, crosswind, tailwind, hwDisplay };
}

export interface LimitCheck {
  exceeded: boolean;
  message: string | null;
}

/** Alert message when crosswind/tailwind exceed their limits (XW first,
 * mirroring the original widget behavior). */
export function checkWindLimits(
  crosswind: number,
  tailwind: number,
  xwLimit: number,
  twLimit: number,
): LimitCheck {
  if (crosswind > xwLimit) return { exceeded: true, message: 'XW LIMIT EXCEEDED' };
  if (tailwind > twLimit) return { exceeded: true, message: 'TW LIMIT EXCEEDED' };
  return { exceeded: false, message: null };
}
