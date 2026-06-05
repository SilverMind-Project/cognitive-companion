import { reactive } from "vue";
import rough from "roughjs";

const gen = rough.generator();

const CACHE_MAX = 500;
const _memo = new Map();

function _evict() {
  if (_memo.size >= CACHE_MAX) {
    _memo.delete(_memo.keys().next().value);
  }
}

function seedFrom(str) {
  let h = 5381;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) + h) ^ str.charCodeAt(i);
    h = h >>> 0;
  }
  return h;
}

function _roundPts(pts) {
  return pts.map(([x, y]) => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]);
}

function path(pts, opts = {}) {
  const { seed = 0, roughness = 1.2, bowing = 1.0 } = opts;
  const key = `${seed}:${JSON.stringify(_roundPts(pts))}`;
  if (_memo.has(key)) return _memo.get(key);
  _evict();
  const drawable = gen.polygon(pts, { seed, roughness, bowing });
  const paths = gen.toPaths(drawable);
  const d = paths[0]?.d ?? "";
  _memo.set(key, d);
  return d;
}

export function useRoughSketch() {
  return {
    state: reactive({}),
    actions: { path, seedFrom },
  };
}
