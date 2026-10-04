import { describe, expect, it } from "vitest";
import { KIND_LABEL, sourceLine } from "./describe";

describe("sourceLine", () => {
  it("names a GitHub issue by repo and number", () =>
    expect(sourceLine("github://pytorch/pytorch", "issue", "196208")).toBe("pytorch/pytorch #196208"));
  it("names a CI run by repo", () =>
    expect(sourceLine("github://microsoft/vscode/actions", "ci", "36464317341")).toBe("microsoft/vscode, run 36464317341"));
  it("names a status page by its host", () =>
    expect(sourceLine("statuspage://www.cloudflarestatus.com", "status", "x")).toBe("www.cloudflarestatus.com"));
  it("names a log by its host", () =>
    expect(sourceLine("syslog://combo", "log", null)).toBe("host combo"));
});

describe("KIND_LABEL", () => {
  it("has words for every kind", () =>
    expect(Object.keys(KIND_LABEL).sort()).toEqual(["ci", "issue", "log", "status", "supercomputer"]));
});
