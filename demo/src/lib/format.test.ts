import { describe, expect, it } from "vitest";
import { dec, joinList, n, pct, ratio, word } from "./format";

describe("format", () => {
  it("groups thousands", () => expect(n(31155)).toBe("31,155"));
  it("keeps at most two decimals", () => expect(dec(0.6312)).toBe("0.63"));
  it("rounds percentages", () => expect(pct(0.912)).toBe("91%"));
  it("writes ratios with one decimal and a times sign", () =>
    expect(ratio(31155, 905)).toBe("34.4×"));
});

describe("word and joinList", () => {
  it("spells one to nine, groups the rest", () => {
    expect(word(1)).toBe("one");
    expect(word(9)).toBe("nine");
    expect(word(10)).toBe("10");
    expect(word(1200)).toBe("1,200");
  });
  it("joins lists in plain English", () => {
    expect(joinList(["a"])).toBe("a");
    expect(joinList(["a", "b"])).toBe("a and b");
    expect(joinList(["a", "b", "c"])).toBe("a, b and c");
  });
});
