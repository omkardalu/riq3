// A tiny scriptable browser on top of jsdom: cookies, real fetch, followed navigations.
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);

// jsdom cannot navigate. Record cross-document navigations so the harness can follow them.
// (Must be patched before jsdom loads: Location-impl destructures `navigate` on import.)
const nav = require("jsdom/lib/jsdom/living/window/navigation.js");
const { serializeURL } = require("whatwg-url");
const origNavigate = nav.navigate;
const noHash = (u) => u.split("#")[0];
nav.navigate = function (window, newURL, flags) {
  const href = serializeURL(newURL);
  if (!flags.reloadTriggered && noHash(href) !== noHash(window.document.URL) && newURL.scheme !== "javascript") {
    (window.__nav ||= []).push({ href, replace: !!flags.replacement });
    return;
  }
  return origNavigate(window, newURL, flags);
};

const { JSDOM, VirtualConsole, CookieJar } = require("jsdom");

export class Browser {
  constructor(base) {
    this.base = base.replace(/\/$/, "");
    this.jar = new CookieJar();
    this.dom = null;
    this.errors = [];
    this.alerts = [];
    this.pending = 0;
    this.visited = [];
    this.session = {}; // sessionStorage survives navigation within a tab
  }

  get window() { return this.dom.window; }
  get document() { return this.dom.window.document; }
  get url() { return new URL(this.window.location.href); }
  get path() { return this.url.pathname; }

  _fetchFor(window) {
    const self = this;
    return async (input, init = {}) => {
      const url = new URL(typeof input === "string" ? input : input.url, window.location.href).href;
      self.pending++;
      try {
        const headers = new Headers(init.headers || {});
        const cookie = self.jar.getCookieStringSync(url);
        if (cookie) headers.set("cookie", cookie);
        let body = init.body;
        if (body && typeof body === "object" && typeof body.entries === "function" && body.constructor.name === "FormData") {
          const fd = new FormData();
          for (const [k, v] of body.entries()) {
            if (typeof v === "string") fd.append(k, v);
            else {
              const buf = await new Promise((resolve, reject) => {
                const r = new window.FileReader();
                r.onload = () => resolve(r.result);
                r.onerror = reject;
                r.readAsArrayBuffer(v);
              });
              fd.append(k, new Blob([buf], { type: v.type }), v.name);
            }
          }
          body = fd;
        }
        const res = await fetch(url, { method: init.method || "GET", headers, body, redirect: "follow" });
        for (const sc of res.headers.getSetCookie()) self.jar.setCookieSync(sc, url);
        return res;
      } finally {
        self.pending--;
      }
    };
  }

  async open(path, hops = 0) {
    const href = new URL(path, this.base + "/").href;
    const self = this;
    const vc = new VirtualConsole();
    vc.on("jsdomError", (e) => {
      if (/Could not load (link|script|img)|Not implemented: (navigation|HTMLFormElement\.prototype\.requestSubmit)/.test(e.message)) return;
      self.errors.push(e.message + (e.detail ? " :: " + e.detail : ""));
    });
    vc.on("error", (...a) => self.errors.push("console.error: " + a.join(" ")));
    const dom = await JSDOM.fromURL(href, {
      cookieJar: this.jar,
      runScripts: "dangerously",
      resources: "usable",
      pretendToBeVisual: true,
      virtualConsole: vc,
      beforeParse(w) {
        w.fetch = self._fetchFor(w);
        w.confirm = () => true;
        w.alert = (m) => self.alerts.push(String(m));
        for (const [k, v] of Object.entries(self.session)) w.sessionStorage.setItem(k, v);
        w.scrollTo = () => {};
        w.HTMLElement.prototype.scrollIntoView = () => {};
      },
    });
    this.dom = dom;
    this.visited.push(dom.window.location.href);
    if (dom.window.document.readyState !== "complete") {
      await new Promise((r) => dom.window.addEventListener("load", r, { once: true }));
    }
    await this.settle(hops);
    return this;
  }

  /** Wait for in-flight requests/timers to finish, following any page navigation. */
  async settle(hops = 0) {
    let quiet = 0;
    for (let i = 0; i < 400 && quiet < 3; i++) {
      await new Promise((r) => setTimeout(r, 25));
      const navs = this.window.__nav;
      if (navs && navs.length) {
        const target = navs.pop();
        this._snapshot();
        if (hops > 10) throw new Error("too many navigations: " + target.href);
        return this.open(target.href, hops + 1);
      }
      quiet = this.pending === 0 ? quiet + 1 : 0;
    }
  }

  _snapshot() {
    const s = this.window.sessionStorage;
    this.session = {};
    for (let i = 0; i < s.length; i++) this.session[s.key(i)] = s.getItem(s.key(i));
  }

  $(sel) { return this.document.querySelector(sel); }
  $$(sel) { return [...this.document.querySelectorAll(sel)]; }
  text(sel) { const el = this.$(sel); return el ? el.textContent.replace(/\s+/g, " ").trim() : null; }
  visible(sel) { const el = this.$(sel); return !!el && this.window.getComputedStyle(el).display !== "none"; }

  fill(sel, value) {
    const el = this.$(sel);
    if (!el) throw new Error("no element " + sel);
    el.value = value;
    el.dispatchEvent(new this.window.Event("input", { bubbles: true }));
    el.dispatchEvent(new this.window.Event("change", { bubbles: true }));
  }

  async click(sel) {
    const el = typeof sel === "string" ? this.$(sel) : sel;
    if (!el) throw new Error("no element " + sel);
    el.click();
    await this.settle();
  }

  async submit(formSel) {
    const form = this.$(formSel);
    form.dispatchEvent(new this.window.Event("submit", { bubbles: true, cancelable: true }));
    await this.settle();
  }

  /** files: [{name, bytes: Buffer|Uint8Array, type}] */
  async chooseFiles(sel, files) {
    const input = this.$(sel);
    const w = this.window;
    const list = files.map((f) => new w.File([f.bytes], f.name, { type: f.type || "" }));
    Object.defineProperty(input, "files", { value: Object.assign(list.slice(), { item: (i) => list[i] }), configurable: true });
    input.dispatchEvent(new w.Event("change", { bubbles: true }));
    await this.settle();
  }

  async api(method, path, json) {
    const csrf = await (await this.window.fetch("/api/csrf")).json();
    const r = await this.window.fetch(path, {
      method,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf.csrf_token },
      body: json === undefined ? undefined : JSON.stringify(json),
    });
    return { status: r.status, body: await r.json().catch(() => ({})) };
  }

  close() { if (this.dom) this.dom.window.close(); }
}

export const PAGES = {
  public: ["login", "create-account", "register", "features", "how-it-works"],
  protected: ["homepage", "upload", "ats-score", "profile", "edit-profile", "change-password"],
};
