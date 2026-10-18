import test from "node:test";
import assert from "node:assert/strict";
import { newBrowser, signedInBrowser } from "./helpers.mjs";
import { PAGES } from "./browser.mjs";

const ALL = [...PAGES.public, ...PAGES.protected];

test("every page has a main landmark, a skip link, a favicon and a Resume IQ title", async () => {
  const { browser: b } = await signedInBrowser();
  for (const p of ALL) {
    await b.open(`/${p}.html`);
    if (b.path !== `/${p}.html`) continue;                       // register.html bounces to step 1 without data
    const skip = b.$(".riq-skip");
    assert.ok(skip, `${p}: skip link`);
    const target = b.document.getElementById(skip.getAttribute("href").slice(1));
    assert.ok(target, `${p}: skip link target exists`);
    assert.ok(target.tagName === "MAIN" || target.getAttribute("role") === "main", `${p}: main landmark`);
    assert.ok(b.$("link[rel=icon]"), `${p}: favicon`);
    assert.match(b.document.title, /^Resume IQ/, p);
    assert.deepEqual(b.errors, [], `${p}: ${b.errors.join("; ")}`);
  }
  b.close();
});

test("public auth pages also have landmarks when signed out", async () => {
  for (const p of ["login", "create-account", "features", "how-it-works"]) {
    const b = newBrowser();
    await b.open(`/${p}.html`);
    assert.ok(b.$(".riq-skip"), p);
    assert.ok(b.$("main, [role=main]"), p);
    b.close();
  }
});

test("favicon is served", async () => {
  const b = newBrowser();
  await b.open("/login.html");
  const r = await b.window.fetch("/favicon.ico");
  assert.equal(r.status, 200);
  assert.match(r.headers.get("content-type"), /svg/);
  const r2 = await b.window.fetch("/assets/img/favicon.svg");
  assert.equal(r2.status, 200);
  b.close();
});

test("features and how-it-works: shared nav shows Login when signed out", async () => {
  for (const p of ["features", "how-it-works"]) {
    const b = newBrowser();
    await b.open(`/${p}.html`);
    assert.ok(b.$(".site-nav"), p);
    assert.equal(b.$(".site-links a.active").textContent, p === "features" ? "Features" : "How It Works");
    assert.ok(b.$("#siteAccount a[href='login.html']"), `${p}: login link`);
    assert.ok(!b.$("#menuButton"), `${p}: no account menu when signed out`);
    assert.ok(b.$(".site-footer"), `${p}: footer`);
    b.close();
  }
});

test("shared nav shows a working account menu when signed in", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/features.html");
  assert.ok(b.$("#menuButton"));
  await b.click("#menuButton");
  assert.ok(b.visible("#dropdown"));
  assert.equal(b.$("#menuButton").getAttribute("aria-expanded"), "true");
  b.document.body.click();                                        // outside click closes
  assert.ok(!b.visible("#dropdown"));
  await b.click("#menuButton");
  b.document.dispatchEvent(new b.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.ok(!b.visible("#dropdown"));
  await b.click("#menuButton");
  await b.click("#profileButton");
  assert.equal(b.path, "/profile.html");
  b.close();
});

test("every nav and footer link on the content pages leads to a working page", async () => {
  const { browser: b } = await signedInBrowser();
  const hrefs = new Set();
  for (const p of ["homepage", "features", "how-it-works"]) {
    await b.open(`/${p}.html`);
    b.$$("header a[href], nav a[href], footer a[href]").forEach((a) => hrefs.add(a.getAttribute("href")));
  }
  assert.ok(hrefs.size >= 6, [...hrefs].join());
  for (const h of hrefs) {
    if (h.startsWith("#")) continue;
    await b.open("/" + h);
    assert.equal(b.path, "/" + h, `${h} should load (not redirect/404)`);
    assert.ok(b.document.title.startsWith("Resume IQ"), h);
    assert.deepEqual(b.errors, [], `${h}: ${b.errors.join("; ")}`);
  }
  b.close();
});

test("homepage: FAQ is complete and accessible, footer navigates, claims are honest", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/homepage.html");
  const faqs = b.$$(".faq");
  assert.equal(faqs.length, 6);
  const btn = faqs[0].querySelector("button");
  assert.equal(btn.getAttribute("aria-expanded"), "false");
  await b.click(btn);
  assert.equal(btn.getAttribute("aria-expanded"), "true");
  assert.ok(faqs[0].classList.contains("open"));
  await b.click(btn);
  assert.equal(btn.getAttribute("aria-expanded"), "false");
  assert.ok(b.$$("footer .footer-links a").length >= 6);
  assert.ok(b.$("main") && b.$("main").contains(b.$("#faq")), "FAQ sits inside the closed <main>");
  const all = b.document.body.textContent;
  assert.doesNotMatch(all, /AI-powered/i);
  assert.match(b.text("#faq"), /rule-based/i);
  assert.match(b.text(".sample-note"), /Sample preview/);
  assert.doesNotMatch(b.text(".analysis-card"), /Formatting/);
  b.close();
});

test("copy no longer claims AI or 10 GB, and typos are gone", async () => {
  for (const p of ["features", "how-it-works", "homepage"]) {
    const b = newBrowser();
    await b.open(`/${p}.html`);
    const text = b.document.body.textContent;
    assert.doesNotMatch(text, /10\s?GB/i, p);
    assert.doesNotMatch(text, /AI[- ]powered|AI Analysis|intelligent AI/i, p);
    assert.doesNotMatch(text, /Mutli|upto/i, p);
    b.close();
  }
  const b = newBrowser();
  await b.open("/features.html");
  assert.equal(b.$$(".feature-card").length, 6);
  await b.open("/how-it-works.html");
  assert.match(b.text(".process"), /5 MB/);
  b.close();
});

test("upload page shows required skills as chips", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  b.fill("#requiredSkills", "Python\nReact, SQL");
  b.$("#requiredSkills").dispatchEvent(new b.window.Event("input", { bubbles: true }));
  assert.deepEqual(b.$$("#skillsPreview .skill-chip").map((c) => c.textContent), ["Python", "React", "SQL"]);
  b.fill("#requiredSkills", "<b>x</b>");
  b.$("#requiredSkills").dispatchEvent(new b.window.Event("input", { bubbles: true }));
  assert.equal(b.$$("#skillsPreview b").length, 0, "skill text is escaped");
  b.close();
});

test("pages declare responsive layouts (viewport + media queries; login box can shrink)", async () => {
  const b = newBrowser();
  for (const p of ALL) {
    await b.open(`/${p}.html`);
    if (b.path !== `/${p}.html`) continue;
    assert.match(b.$("meta[name=viewport]").getAttribute("content"), /width=device-width/, p);
  }
  const html = await (await b.window.fetch("/login.html")).text();
  assert.match(html, /max-width:\s*100%/);
  assert.match(html, /@media \(max-width: 480px\)/);
  b.close();
});
