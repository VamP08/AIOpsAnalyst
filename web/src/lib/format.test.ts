import { describe, expect, it } from "vitest";
import { dec, n, pct, ratio } from "./format";

describe("format", () => {
  it("groups thousands", () => expect(n(31155)).toBe("31,155"));
  it("keeps at most two decimals", () => expect(dec(0.6312)).toBe("0.63"));
  it("rounds percentages", () => expect(pct(0.912)).toBe("91%"));
  it("writes ratios with one decimal and a times sign", () =>
    expect(ratio(31155, 905)).toBe("34.4×"));
});
