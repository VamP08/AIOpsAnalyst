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

import { outcomeOf } from "./outcomes";

describe("outcomeOf", () => {
  it("maps tiers the way the export does", () => {
    expect(outcomeOf("escalate", "crash", policy.routes)).toBe("person");
    expect(outcomeOf("suggest", "crash", policy.routes)).toBe("draft");
    expect(outcomeOf("abstain", "error", policy.routes)).toBe("unsure");
    expect(outcomeOf("auto", "crash", policy.routes)).toBe("ticket");
    expect(outcomeOf("auto", "question", policy.routes)).toBe("dropped");
  });
  it("agrees with the exported outcome for every specimen", () => {
    for (const s of specimens) expect(outcomeOf(s.route.tier, s.verdict.category, policy.routes)).toBe(s.outcome);
  });
});

import { readFileSync } from "node:fs";

describe("clusters.json", () => {
  it("every row's outcome follows from its tier and category", () => {
    const rows = JSON.parse(readFileSync(new URL("../../public/data/clusters.json", import.meta.url), "utf-8"));
    for (const row of rows.filter((r: { tier?: string }) => r.tier))
      expect(outcomeOf(row.tier, row.category, policy.routes)).toBe(row.outcome);
  });
});
