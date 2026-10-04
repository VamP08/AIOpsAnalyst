import type { Kind } from "./data";

/** What a reader calls each kind of source. */
export const KIND_LABEL: Record<Kind, string> = {
  issue: "GitHub issue",
  ci: "Failed CI run",
  status: "Status-page incident",
  log: "Server log",
  supercomputer: "Supercomputer log",
};

/** Plural, for counts: "330 GitHub issues". */
export const KIND_PLURAL: Record<Kind, string> = {
  issue: "GitHub issues",
  ci: "failed CI runs",
  status: "status-page incidents",
  log: "server log lines",
  supercomputer: "supercomputer log lines",
};

/** Where one event came from, in words: the repo and number, the host. */
export function sourceLine(source: string, kind: Kind, subject: string | null): string {
  const path = source.replace(/^[a-z]+:\/\//, "");
  if (kind === "issue") return `${path} #${subject}`;
  if (kind === "ci") return `${path.replace(/\/actions$/, "")}, run ${subject}`;
  if (kind === "status") return path;
  return `host ${path.split("/")[0]}`;
}
