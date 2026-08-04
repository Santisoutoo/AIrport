// Shared mutable state for the SMR ground radar, owned here so the render
// and interaction modules can collaborate without a god-file.

import type { AirportGraph } from '../types/api';
import { geoToSVG, type Point, type SmrBounds } from './projection';

export interface ViewBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface MaxBounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export const smrState = {
  graph: null as AirportGraph | null,
  bounds: null as SmrBounds | null,
  viewBox: { x: 0, y: 0, w: 100, h: 100 } as ViewBox,
  maxBounds: { minX: 0, minY: 0, maxX: 100, maxY: 100 } as MaxBounds,
  activeILSRunway: null as string | null,
};

/** Project through the current bounds (viewBox centre fallback). */
export function toSVG(lat: number, lon: number): Point {
  return geoToSVG(smrState.bounds, lat, lon);
}

export function smrSvg(): SVGSVGElement | null {
  return document.querySelector<SVGSVGElement>('#smr-svg');
}

/** Numeric attribute helper for the data-base-* rescale attributes. */
export function attrNum(el: Element, name: string): number {
  return parseFloat(el.getAttribute(name) ?? '0');
}
