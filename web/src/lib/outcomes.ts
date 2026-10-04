export type Outcome = "ticket" | "person" | "draft" | "dropped" | "unsure";

export const OUTCOMES: { key: Outcome; label: string; sentence: string; glyph: string }[] = [
  { key: "ticket",  label: "Filed as a ticket",          sentence: "Sure enough, and something a team should fix. It goes to the tracker.", glyph: "■" },
  { key: "person",  label: "Wakes a person",             sentence: "Critical, or serious and uncertain. A human looks before anything happens.", glyph: "▲" },
  { key: "draft",   label: "Drafted, waits for approval", sentence: "Fairly sure. A ticket is drafted and a person approves it.", glyph: "◆" },
  { key: "dropped", label: "Routine, dropped",           sentence: "Sure it is routine chatter or a question. Recorded, nothing sent.", glyph: "●" },
  { key: "unsure",  label: "Not sure, recorded",         sentence: "Too unsure to act and nothing forces a human. Recorded as unsure, on purpose.", glyph: "○" },
];
