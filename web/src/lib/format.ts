const grouped = new Intl.NumberFormat("en-US");
export const n = (x: number) => grouped.format(x);
export const dec = (x: number, places = 2) => x.toFixed(places);
export const pct = (x: number) => `${Math.round(x * 100)}%`;
export const ratio = (a: number, b: number) => `${(a / b).toFixed(1)}×`;
