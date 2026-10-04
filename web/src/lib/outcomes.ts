export type Outcome = "ticket" | "person" | "draft" | "dropped" | "unsure";

export const OUTCOMES: { key: Outcome; label: string; sentence: string; glyph: string }[] = [
  { key: "ticket",  label: "Becomes a ticket",          sentence: "Sure enough, and something a team should fix. The rulebook sends it to the tracker.", glyph: "■" },
  { key: "person",  label: "Wakes a person",             sentence: "Critical, or serious and uncertain. A human looks before anything happens.", glyph: "▲" },
  { key: "draft",   label: "Drafted, waits for approval", sentence: "Fairly sure. A ticket is drafted and a person approves it.", glyph: "◆" },
  { key: "dropped", label: "Routine, dropped",           sentence: "Sure it is routine chatter or a question. Recorded, nothing sent.", glyph: "●" },
  { key: "unsure",  label: "Not sure, recorded",         sentence: "Too unsure to act and nothing forces a human. Recorded as unsure, on purpose.", glyph: "○" },
];

const TIER_OUTCOME: Record<string, Outcome> = { escalate: "person", suggest: "draft", abstain: "unsure" };

/** Which of the five outcomes a verdict ends in: the same rule the export
 *  applies, for data the export did not route (the live feed). */
export function outcomeOf(
  tier: string,
  category: string,
  routes: { tiers: string[]; categories?: string[] }[],
): Outcome {
  if (tier in TIER_OUTCOME) return TIER_OUTCOME[tier];
  const routed = routes.some((r) => r.tiers.includes(tier) && (!r.categories || r.categories.includes(category)));
  return routed ? "ticket" : "dropped";
}
