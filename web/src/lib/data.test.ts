import { describe, expect, it } from "vitest";
import { specimens, stats, policy } from "./data";
import { OUTCOMES } from "./outcomes";

describe("data", () => {
  it("outcomes partition the clusters", () => {
    const total = OUTCOMES.reduce((s, o) => s + stats.outcomes[o.key], 0);
    expect(total).toBe(stats.clusters);
  });
  it("every specimen has a slug and a known outcome", () => {
    const keys = OUTCOMES.map((o) => o.key);
    for (const s of specimens) expect(keys).toContain(s.outcome);
    expect(new Set(specimens.map(s => s.slug)).size).toBe(specimens.length);
  });
  it("the gate has five ordered rules", () => expect(policy.gate).toHaveLength(5));
});
