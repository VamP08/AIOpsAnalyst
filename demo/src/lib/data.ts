import statsJson from "../../public/data/stats.json";
import specimensJson from "../../public/data/specimens.json";
import policyJson from "../../public/data/policy.json";
import scorecardsJson from "../../public/data/scorecards.json";
import liveJson from "../../public/data/live.json";
import escalationsJson from "../../public/data/escalations.json";
import type { Outcome } from "./outcomes";

export type Kind = "issue" | "ci" | "status" | "log" | "supercomputer";

export interface Stats {
  events: number; clusters: number; compression: number; tickets: number;
  route_matched: number; outcomes: Record<Outcome, number>;
  by_kind: Record<Kind, number>; events_by_kind: Record<Kind, number>; by_tier: Record<string, number>; generated: string;
}
export interface Specimen {
  slug: string; outcome: Outcome;
  input: { source: string; type: string; kind: Kind; subject: string | null; time: string | null;
           title: string; url: string | null; body: string };
  cluster: { id: string; label: string; size: number; siblings: string[] };
  verdict: { category: string; severity: string; confidence: number; summary: string };
  route: { tier: string; rule: number; why: string;
           ticket: { key: string; type: string; summary: string } | null };
}
export interface Policy {
  thresholds: { auto: number; suggest: number };
  gate: { condition: string; tier: string }[];
  routes: { tiers: string[]; categories?: string[]; sink: string }[];
}

const SLUGS: Record<string, string> = {
  issue: "github-issue", ci: "ci-failure", status: "status-incident",
  log: "server-log", supercomputer: "supercomputer-log",
};
export const specimenSlug = (s: Omit<Specimen, "slug">) =>
  s.outcome === "unsure" ? "unsure-issue" : SLUGS[s.input.kind];

export const stats = statsJson as unknown as Stats;
export const specimens: Specimen[] = (specimensJson as unknown as Omit<Specimen, "slug">[])
  .map((s) => ({ ...s, slug: specimenSlug(s) }));
export const policy = policyJson as Policy;
export const scorecards = scorecardsJson as any;
export const live = liveJson as any;
export const escalations = escalationsJson as any[];
