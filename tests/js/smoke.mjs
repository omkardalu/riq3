// Loads every page in jsdom, runs its scripts and fails on any script error.
// Usage: node smoke.mjs            (pages from ../../web/pages or repo root)
import { JSDOM, VirtualConsole } from "jsdom";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "../..");
const dir = fs.existsSync(path.join(root, "web/pages")) ? path.join(root, "web/pages") : root;

let failures = 0;
for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".html")).sort()) {
  const errors = [];
  const vc = new VirtualConsole();
  vc.on("jsdomError", (e) => {
    if (/Not implemented: navigation/.test(e.message)) return; // location.href changes are fine
    errors.push(e.message);
  });
  const dom = await JSDOM.fromFile(path.join(dir, file), {
    url: "http://localhost/",
    runScripts: "dangerously",
    pretendToBeVisual: true,
    virtualConsole: vc,
    beforeParse(w) {
      w.fetch = async () => ({ ok: false, status: 401, json: async () => ({}) });
      w.confirm = () => true;
      w.alert = () => {};
    },
  });
  await new Promise((r) => setTimeout(r, 50));
  const title = dom.window.document.title;
  const ok = errors.length === 0 && title.trim().length > 0;
  console.log(`${ok ? "PASS" : "FAIL"}  ${file}  (${title})`);
  errors.forEach((e) => console.log("      ", e));
  if (!ok) failures++;
  dom.window.close();
}
process.exit(failures ? 1 : 0);
