// Every number a page shows must exist in the data it was built from.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const DATA = "public/data", DIST = "dist";
const NUM = /\d{1,3}(?:,\d{3})+|\d+\.\d+%?|\d{3,}%?/g;
const known = new Set();
const add = (v) => {
  for (const s of [String(v), v.toLocaleString("en-US"), v.toFixed(1), v.toFixed(2), v.toFixed(3),
                   `${Math.round(v * 100)}%`]) known.add(s);
};
const walk = (v) => {
  if (Array.isArray(v)) v.forEach(walk);
  else if (v && typeof v === "object") Object.values(v).forEach(walk);
  else if (typeof v === "number") add(v);
  else if (typeof v === "string") for (const m of v.matchAll(NUM)) known.add(m[0]);
};
for (const f of readdirSync(DATA)) if (f.endsWith(".json")) walk(JSON.parse(readFileSync(join(DATA, f), "utf8")));

const pages = [];
const scan = (d) => readdirSync(d).forEach((f) => {
  const p = join(d, f);
  statSync(p).isDirectory() ? scan(p) : p.endsWith(".html") && pages.push(p);
});
scan(DIST);

const bad = [];
for (const p of pages) {
  const text = readFileSync(p, "utf8")
    .replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>|<time[\s\S]*?<\/time>|<[^>]+>/g, " ");
  for (const m of text.matchAll(NUM)) if (!known.has(m[0])) bad.push(`${p}: ${m[0]}`);
}
if (bad.length) { console.error("numbers with no source in data/:\n" + bad.join("\n")); process.exit(1); }
console.log(`check-numbers: ${pages.length} pages, every number traced`);
