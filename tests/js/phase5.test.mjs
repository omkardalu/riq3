import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { signedInBrowser } from "./helpers.mjs";

const FIX = process.env.FIXTURES_DIR;
const file = (name, as) => ({ name: as || name, bytes: fs.readFileSync(path.join(FIX, name)), type: "" });

/** Upload resumes + run an analysis through the API; returns the job id. */
async function seed(b, files, skills = "Python, SQL, Docker", title = "Backend Dev", jd = "") {
  await b.open("/upload.html");
  await b.chooseFiles("#resumeFile", files);
  const resumes = (await b.api("GET", "/api/resumes")).body.resumes;
  const job = (await b.api("POST", "/api/jobs", { title, required_skills: skills, description: jd })).body.job;
  for (const r of resumes) await b.api("POST", "/api/analyses", { job_id: job.id, resume_id: r.id });
  return job.id;
}
const rowNames = (b) => b.$$("#resultsBody tr").map((r) => r.children[0].textContent.replace(/\s+/g, " ").trim());
const ALL = () => [file("rahul.pdf"), file("priya.docx"), file("arjun.docx"), file("scanned.pdf")];

test("empty state for an account with no analyses", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/ats-score.html");
  assert.match(b.text("#stateBox"), /No analyses yet/);
  assert.ok(b.$("#stateBox a[href='upload.html']"));
  assert.equal(b.$$("#resultsBody tr").length, 0);
  assert.deepEqual(b.errors, []);
  b.close();
});

test("shows the real analysis results, never the old placeholder applicants", async () => {
  const { browser: b } = await signedInBrowser();
  await seed(b, ALL());
  await b.open("/ats-score.html");
  const names = rowNames(b);
  assert.equal(names.length, 4);
  assert.ok(names.some((n) => n.startsWith("Rahul Kumar")));
  assert.ok(names.some((n) => n.startsWith("Arjun Reddy")));
  assert.ok(!b.text("body").includes("Sneha Patel") && !b.text("body").includes("Meera Das"));
  // default sort: score high to low, unscored (unsupported) last
  const scores = b.$$("#resultsBody tr").map((r) => parseFloat(r.children[1].textContent));
  const real = scores.filter((s) => !Number.isNaN(s));
  assert.deepEqual(real, [...real].sort((x, y) => y - x));
  assert.ok(Number.isNaN(scores[scores.length - 1]));
  assert.match(b.text("#resultsBody"), /Unsupported/);
  assert.match(b.text("#resultCount"), /Showing 4 of 4/);
  assert.deepEqual(b.errors, []);
  b.close();
});

test("results survive a refresh (persisted in the database)", async () => {
  const { browser: b } = await signedInBrowser();
  await seed(b, [file("rahul.pdf")]);
  await b.open("/ats-score.html");
  const first = b.text("#resultsBody");
  await b.open("/ats-score.html");
  assert.equal(b.text("#resultsBody"), first);
  assert.match(first, /Rahul Kumar/);
  b.close();
});

test("search, status filter and sorting work and show a no-match state", async () => {
  const { browser: b } = await signedInBrowser();
  await seed(b, ALL());
  await b.open("/ats-score.html");

  b.fill("#searchBox", "arjun");
  await b.settle();
  await new Promise((r) => setTimeout(r, 400)); await b.settle();
  assert.deepEqual(rowNames(b).map((n) => n.split(" ")[0]), ["Arjun"]);

  b.fill("#searchBox", "zzz-nobody");
  await new Promise((r) => setTimeout(r, 400)); await b.settle();
  assert.match(b.text("#stateBox"), /No matching applicants/);

  b.fill("#searchBox", "");
  await new Promise((r) => setTimeout(r, 400)); await b.settle();
  assert.equal(rowNames(b).length, 4);

  b.fill("#statusFilter", "unsupported");
  b.$("#statusFilter").dispatchEvent(new b.window.Event("change"));
  await b.settle();
  assert.equal(rowNames(b).length, 1);
  assert.match(rowNames(b)[0], /Unsupported/);

  b.fill("#statusFilter", "");
  b.$("#statusFilter").dispatchEvent(new b.window.Event("change"));
  await b.settle();
  b.fill("#sortSelect", "name:asc");
  b.$("#sortSelect").dispatchEvent(new b.window.Event("change"));
  await b.settle();
  const sorted = rowNames(b).map((n) => n.toLowerCase());
  assert.deepEqual(sorted, [...sorted].sort());
  b.close();
});

test("opening an applicant shows real details, a score breakdown and a download link", async () => {
  const { browser: b } = await signedInBrowser();
  await seed(b, [file("rahul.pdf")], "Python, SQL, Docker", "Backend Dev", "Python backend developer with SQL experience.");
  await b.open("/ats-score.html");
  await b.click("#resultsBody tr");
  assert.ok(b.visible("#applicantDetails") && !b.visible("#applicantList"));
  assert.equal(b.text("#detailName"), "Rahul Kumar");
  assert.equal(b.text("#detailEmail"), "rahul@example.com");
  assert.equal(b.text("#infoPhone"), "+91 98765 43210");
  assert.deepEqual(b.$$("#matchedSkills .matched-skill").map((x) => x.textContent), ["Python", "SQL"]);
  assert.deepEqual(b.$$("#missingSkills .missing-skill").map((x) => x.textContent), ["Docker"]);
  assert.match(b.text("#infoEducation"), /b\.tech in computer science/i);
  assert.match(b.text("#infoWeaknesses"), /Docker/);
  assert.match(b.text("#infoBreakdown"), /Required skills/);
  assert.match(b.text("#infoBreakdown"), /version v1/);
  assert.match(b.text("#detailScore"), /^\d+(\.\d)?%$/);
  assert.equal(b.$("#detailActions a").getAttribute("href").startsWith("/api/resumes/"), true);
  // the shown score equals the stored one
  const api = (await b.api("GET", "/api/analyses")).body.analyses[0];
  assert.equal(parseFloat(b.text("#detailScore")), Math.round(api.score * 10) / 10);

  await b.click("#backBtn");
  assert.ok(b.visible("#applicantList") && !b.visible("#applicantDetails"));
  b.close();
});

test("unsupported resumes explain why and show no invented numbers", async () => {
  const { browser: b } = await signedInBrowser();
  await seed(b, [file("scanned.pdf")]);
  await b.open("/ats-score.html");
  await b.click("#resultsBody tr");
  assert.match(b.text("#detailNotice"), /OCR is not supported/);
  assert.equal(b.text("#detailScore"), "\u2014");
  assert.match(b.text("#infoBreakdown"), /No score was calculated/);
  b.close();
});

test("deep link opens the right applicant", async () => {
  const { browser: b } = await signedInBrowser();
  const jobId = await seed(b, [file("rahul.pdf"), file("arjun.docx")]);
  const arjun = (await b.api("GET", `/api/analyses?job_id=${jobId}&q=arjun`)).body.analyses[0];
  await b.open(`/ats-score.html?job=${jobId}&a=${arjun.id}`);
  assert.equal(b.text("#detailName"), "Arjun Reddy");
  b.close();
});

test("history: several runs can be switched between and deleted", async () => {
  const { browser: b } = await signedInBrowser();
  const j1 = await seed(b, [file("rahul.pdf")], "Python", "Run A");
  const resumes = (await b.api("GET", "/api/resumes")).body.resumes;
  const j2 = (await b.api("POST", "/api/jobs", { title: "Run B", required_skills: "Docker, AWS" })).body.job.id;
  await b.api("POST", "/api/analyses", { job_id: j2, resume_id: resumes[0].id });

  await b.open("/ats-score.html");
  assert.equal(b.$$("#jobSelect option").length, 2);
  const scoreOf = () => b.$("#resultsBody tr").children[1].textContent;
  b.fill("#jobSelect", String(j1)); b.$("#jobSelect").dispatchEvent(new b.window.Event("change")); await b.settle();
  const a = scoreOf();
  b.fill("#jobSelect", String(j2)); b.$("#jobSelect").dispatchEvent(new b.window.Event("change")); await b.settle();
  assert.notEqual(a, scoreOf());

  await b.click("#deleteJobBtn");
  assert.equal(b.$$("#jobSelect option").length, 1);
  assert.equal((await b.api("GET", "/api/jobs")).body.jobs.length, 1);
  b.close();
});

test("a load failure shows an error with a working retry", async () => {
  const { browser: b } = await signedInBrowser();
  await seed(b, [file("rahul.pdf")]);
  await b.open("/ats-score.html");
  const real = b.window.fetch;
  let down = true;
  b.window.fetch = (u, i) => (down && String(u).includes("/api/analyses") ? Promise.reject(new TypeError("offline")) : real(u, i));
  b.fill("#sortSelect", "name:asc");
  b.$("#sortSelect").dispatchEvent(new b.window.Event("change"));
  await b.settle();
  assert.match(b.text("#stateBox"), /Could not load results/);
  down = false;
  await b.click("#stateBox button");
  assert.equal(b.$$("#resultsBody tr").length, 1);
  b.close();
});

test("hostile file names are shown as text, never executed", async () => {
  const { browser: b } = await signedInBrowser();
  await seed(b, [file("scanned.pdf", "<img src=x onerror=window.__xss=1>.pdf")]);
  await b.open("/ats-score.html");
  assert.equal(b.window.__xss, undefined);
  assert.equal(b.$$("#resultsBody img").length, 0);
  assert.match(b.text("#resultsBody"), /<img src=x/i);
  b.close();
});

test("another account sees none of my results", async () => {
  const { browser: a } = await signedInBrowser();
  const jobId = await seed(a, [file("rahul.pdf")]);
  const { browser: other } = await signedInBrowser();
  await other.open(`/ats-score.html?job=${jobId}`);
  assert.match(other.text("#stateBox"), /No analyses yet/);
  assert.equal((await other.api("GET", `/api/analyses?job_id=${jobId}`)).status, 404);
  a.close(); other.close();
});
