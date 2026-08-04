// Pure geographic → SVG projection math for the SMR ground radar.
// No DOM, no module state — everything takes explicit inputs.

import type { AirportGraph } from '../types/api';

export interface SmrBounds {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
  cosLat: number;
}

export interface Point {
  x: number;
  y: number;
}

export const SMR_PADDING = 5;
export const SMR_SIZE = 100;

/** Bounding box of every node/stand/runway end, with margin and the
 * cosine-of-latitude correction used by the projection. */
export function computeSmrBounds(graph: AirportGraph): SmrBounds | null {
  const lats: number[] = [];
  const lons: number[] = [];

  Object.values(graph.nodes).forEach((n) => {
    lats.push(n.lat);
    lons.push(n.lon);
  });
  graph.stands.forEach((s) => {
    lats.push(s.lat);
    lons.push(s.lon);
  });
  graph.runways.forEach((r) => {
    lats.push(r.end1.lat, r.end2.lat);
    lons.push(r.end1.lon, r.end2.lon);
  });

  if (lats.length === 0) return null;

  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);

  const latMargin = (maxLat - minLat) * 0.08;
  const lonMargin = (maxLon - minLon) * 0.08;

  // Cosine correction: at this latitude, 1° lon is shorter than 1° lat
  const centerLat = (minLat + maxLat) / 2;
  const cosLat = Math.cos((centerLat * Math.PI) / 180);

  return {
    minLat: minLat - latMargin,
    maxLat: maxLat + latMargin,
    minLon: minLon - lonMargin,
    maxLon: maxLon + lonMargin,
    cosLat,
  };
}

/** Convert GPS lat/lon to SVG x/y (0-100 viewBox), preserving aspect ratio.
 * North (high latitude) maps to the top. */
export function geoToSVG(bounds: SmrBounds | null, lat: number, lon: number): Point {
  if (!bounds) return { x: 50, y: 50 };

  const dLat = bounds.maxLat - bounds.minLat;
  const dLon = (bounds.maxLon - bounds.minLon) * bounds.cosLat;

  const usable = SMR_SIZE - 2 * SMR_PADDING;
  const scale = usable / Math.max(dLat, dLon);

  const mapW = dLon * scale;
  const mapH = dLat * scale;
  const offX = SMR_PADDING + (usable - mapW) / 2;
  const offY = SMR_PADDING + (usable - mapH) / 2;

  const x = offX + (lon - bounds.minLon) * bounds.cosLat * scale;
  const y = offY + (bounds.maxLat - lat) * scale;
  return { x, y };
}

/** Project a new geographic point from (lat, lon) along a bearing for a
 * distance in nautical miles (flat-earth approximation, fine at SMR range). */
export function projectGeoFromBearing(
  lat: number,
  lon: number,
  bearingDeg: number,
  distNm: number,
): { lat: number; lon: number } {
  const br = (bearingDeg * Math.PI) / 180;
  const dLat = (distNm / 60) * Math.cos(br);
  const latRad = (lat * Math.PI) / 180;
  const dLon = ((distNm / 60) * Math.sin(br)) / Math.cos(latRad);
  return { lat: lat + dLat, lon: lon + dLon };
}

/** Great-circle initial bearing (degrees 0-360) from point 1 to point 2. */
export function bearingDeg(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const l1 = (lat1 * Math.PI) / 180;
  const l2 = (lat2 * Math.PI) / 180;
  const dl = ((lon2 - lon1) * Math.PI) / 180;
  const y = Math.sin(dl) * Math.cos(l2);
  const x = Math.cos(l1) * Math.sin(l2) - Math.sin(l1) * Math.cos(l2) * Math.cos(dl);
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
}

/** Point on the label-box boundary nearest to the aircraft dot, found by
 * ray-casting from the box centre toward the dot. */
export function leaderAttachPoint(
  dotX: number,
  dotY: number,
  boxX: number,
  boxY: number,
  boxW: number,
  boxH: number,
): Point {
  const cx = boxX + boxW / 2;
  const cy = boxY + boxH / 2;
  const vx = dotX - cx;
  const vy = dotY - cy;
  if (vx === 0 && vy === 0) return { x: boxX, y: cy };

  let tMin = Infinity,
    bestX = boxX,
    bestY = cy;
  let t: number, iy: number, ix: number;

  if (vx !== 0) {
    t = (boxX - cx) / vx;
    if (t > 0) {
      iy = cy + t * vy;
      if (iy >= boxY && iy <= boxY + boxH && t < tMin) {
        tMin = t;
        bestX = boxX;
        bestY = iy;
      }
    }
    t = (boxX + boxW - cx) / vx;
    if (t > 0) {
      iy = cy + t * vy;
      if (iy >= boxY && iy <= boxY + boxH && t < tMin) {
        tMin = t;
        bestX = boxX + boxW;
        bestY = iy;
      }
    }
  }
  if (vy !== 0) {
    t = (boxY - cy) / vy;
    if (t > 0) {
      ix = cx + t * vx;
      if (ix >= boxX && ix <= boxX + boxW && t < tMin) {
        tMin = t;
        bestX = ix;
        bestY = boxY;
      }
    }
    t = (boxY + boxH - cy) / vy;
    if (t > 0) {
      ix = cx + t * vx;
      if (ix >= boxX && ix <= boxX + boxW && t < tMin) {
        tMin = t;
        bestX = ix;
        bestY = boxY + boxH;
      }
    }
  }
  return { x: bestX, y: bestY };
}
