const grouped = new Intl.NumberFormat("en-US");
export const n = (x: number) => grouped.format(x);
export const dec = (x: number, places = 2) => x.toFixed(places);
export const pct = (x: number) => `${Math.round(x * 100)}%`;
const WORDS = ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine"];
export const word = (x: number) => (x >= 1 && x <= 9 ? WORDS[x - 1] : n(x));
export const joinList = (xs: string[]) =>
  xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`;
export const ratio = (a: number, b: number) => `${(a / b).toFixed(1)}×`;
