import { describe, expect, it } from 'vitest';
import { nearestInDirection } from './spatialNav';

/** A stand-in element that only needs to answer getBoundingClientRect for the geometry. */
function box(left: number, top: number, width = 100, height = 24): HTMLElement {
  const rect = {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
    x: left,
    y: top,
    toJSON: () => ({}),
  } as DOMRect;
  return { getBoundingClientRect: () => rect } as unknown as HTMLElement;
}

describe('nearestInDirection', () => {
  it('moves along a row to the closer neighbour', () => {
    const current = box(100, 0);
    const near = box(220, 0);
    const far = box(400, 0);
    const behind = box(0, 0);

    expect(nearestInDirection(current, [near, far, behind], 'right')).toBe(near);
    expect(nearestInDirection(current, [near, far, behind], 'left')).toBe(behind);
  });

  it('drops down to the nearest element below', () => {
    const current = box(0, 0);
    const below = box(0, 100);
    const lower = box(0, 300);

    expect(nearestInDirection(current, [below, lower], 'down')).toBe(below);
  });

  it('prefers the on-axis candidate over a closer off-axis one', () => {
    const current = box(0, 0);
    const aligned = box(0, 120);
    const offset = box(160, 90); // closer as-the-crow-flies, but well off to the side

    expect(nearestInDirection(current, [aligned, offset], 'down')).toBe(aligned);
  });

  it('returns null when nothing lies in the direction', () => {
    const current = box(0, 0);
    const below = box(0, 100);

    expect(nearestInDirection(current, [below], 'up')).toBeNull();
    expect(nearestInDirection(current, [], 'down')).toBeNull();
  });

  it('treats a slightly overlapping element as ahead (stacked cards)', () => {
    const current = box(0, 0, 100, 50);
    const stacked = box(0, 49); // its top sits a pixel above current's bottom

    expect(nearestInDirection(current, [stacked], 'down')).toBe(stacked);
  });
});
