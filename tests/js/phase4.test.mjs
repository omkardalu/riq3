import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { signedInBrowser } from "./helpers.mjs";

const FIX = process.env.FIXTURES_DIR;
const file = (name) => ({ name, bytes: fs.readFileSync(path.join(FIX, name)), type: "" });

test("Get Started analyzes every selected resume and reports real results", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  await b.chooseFiles("#resumeFile", [file("rahul.pdf"), file("priya.docx"), file("scanned.pdf")]);
  b.fill("#requiredSkills", "Python\nSQL\nDocker");
  b.fill("#jobDescription", "Backend developer using Python and SQL.");
  await b.click("#startButton");

  const t = b.text("#analysisResults");
  assert.match(t, /Analysis results/);
  assert.match(t, /Rahul Kumar/);
  assert.match(t, /2 of 3 skills/);                 // Rahul: Python + SQL, no Docker
  assert.match(t, /Priya Sharma/);
  assert.match(t, /Unsupported/);                   // scanned PDF is never scored
  assert.match(t, /OCR is not supported/);
  assert.match(b.text("#pageMessage"), /2 of 3 resume\(s\) scored/);
  assert.deepEqual(b.errors, []);

  // results are persisted server-side, not just painted
  const jobs = (await b.api("GET", "/api/jobs")).body.jobs;
  assert.equal(jobs.length, 1);
  const list = (await b.api("GET", `/api/analyses?job_id=${jobs[0].id}`)).body;
  assert.equal(list.total, 3);
  const scores = list.analyses.filter((a) => a.status === "completed").map((a) => a.score);
  assert.equal(scores.length, 2);
  assert.ok(scores.every((s) => s > 0 && s <= 100));
  b.close();
});

test("only checked resumes are analyzed", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  await b.chooseFiles("#resumeFile", [file("rahul.pdf"), file("priya.docx")]);
  const box = b.$$("#fileList input[type=checkbox]")[0];
  box.checked = false;
  box.dispatchEvent(new b.window.Event("change", { bubbles: true }));
  b.fill("#requiredSkills", "Python");
  await b.click("#startButton");
  const jobs = (await b.api("GET", "/api/jobs")).body.jobs;
  assert.equal((await b.api("GET", `/api/analyses?job_id=${jobs[0].id}`)).body.total, 1);
  b.close();
});

test("the same inputs give the same score twice", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  await b.chooseFiles("#resumeFile", [file("rahul.pdf")]);
  b.fill("#requiredSkills", "Python, SQL, Git, Docker");
  b.fill("#jobDescription", "Python engineer with SQL and web application experience.");
  await b.click("#startButton");
  await b.click("#startButton");
  const jobs = (await b.api("GET", "/api/jobs")).body.jobs;
  const scores = [];
  for (const j of jobs) scores.push((await b.api("GET", `/api/analyses?job_id=${j.id}`)).body.analyses[0].score);
  assert.equal(scores.length, 2);
  assert.equal(scores[0], scores[1]);
  b.close();
});
