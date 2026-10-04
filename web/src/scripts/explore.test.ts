import { describe, expect, it } from "vitest";
import { filterClusters } from "./explore";

const rows: any[] = [
  { id: "a", label: "Out of Memory", summary: "oom", outcome: "person", kind: "log", category: "crash", size: 9 },
  { id: "b", label: "CI failed", summary: "tests", outcome: "ticket", kind: "ci", category: "error", size: 3 },
];

describe("filterClusters", () => {
  it("filters by outcome", () => expect(filterClusters(rows, { outcome: "ticket" }).map(r => r.id)).toEqual(["b"]));
  it("searches label and summary, case-insensitively", () =>
    expect(filterClusters(rows, { q: "MEMORY" }).map(r => r.id)).toEqual(["a"]));
  it("combines filters", () => expect(filterClusters(rows, { kind: "log", category: "error" })).toEqual([]));
});
