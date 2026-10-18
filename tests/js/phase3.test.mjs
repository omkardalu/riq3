import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { signedInBrowser } from "./helpers.mjs";

const FIX = process.env.FIXTURES_DIR;
const file = (name, type) => ({ name, bytes: fs.readFileSync(path.join(FIX, name)), type: type || "" });
const rows = (b) => b.$$("#fileList .file-item");
const names = (b) => rows(b).map((r) => r.querySelector(".file-item-name span").textContent);

test("upload page starts empty with real limits shown", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  assert.match(b.text("#fileList"), /No resumes uploaded yet/);
  assert.equal(b.text("#fileCount"), "0");
  assert.match(b.text("#uploadHelp"), /5 MB/);
  assert.deepEqual(b.errors, []);
  b.close();
});

test("uploaded resumes are saved on the server and still listed after a refresh", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  await b.chooseFiles("#resumeFile", [file("rahul.pdf"), file("priya.docx")]);
  assert.deepEqual(names(b).sort(), ["priya.docx", "rahul.pdf"]);
  assert.equal(b.text("#fileCount"), "2");

  await b.open("/upload.html");                       // refresh
  assert.deepEqual(names(b).sort(), ["priya.docx", "rahul.pdf"]);
  assert.equal(b.text("#fileCount"), "2");
  assert.notEqual(b.text("#totalStorage"), "0 B");
  assert.equal(b.$$("#fileList input[type=checkbox]:checked").length, 2);
  b.close();
});

test("invalid files are explained next to the file, nothing is saved", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  await b.chooseFiles("#resumeFile", [
    { name: "notes.txt", bytes: Buffer.from("hello") },
    { name: "old.doc", bytes: Buffer.from("x") },
    { name: "empty.pdf", bytes: Buffer.from("") },
    { name: "fake.pdf", bytes: Buffer.from("this is not a pdf") },
  ]);
  const t = b.text("#fileList");
  assert.match(t, /Only PDF and DOCX/);
  assert.match(t, /Legacy \.doc/);
  assert.match(t, /empty/i);
  assert.match(t, /not a valid PDF/);
  const api = await b.api("GET", "/api/resumes");
  assert.equal(api.body.resumes.length, 0);
  // dismiss clears the row
  await b.click("[data-dismiss]");
  assert.equal(rows(b).length, 3);
  b.close();
});

test("duplicate upload is rejected with a clear message", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  await b.chooseFiles("#resumeFile", [file("rahul.pdf")]);
  await b.chooseFiles("#resumeFile", [{ ...file("rahul.pdf"), name: "copy.pdf" }]);
  assert.match(b.text("#fileList"), /Already uploaded/);
  assert.equal(b.text("#fileCount"), "1");
  b.close();
});

test("a network failure can be retried safely", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  const realFetch = b.window.fetch;
  let failed = false;
  b.window.fetch = (url, init) => {
    if (!failed && String(url).includes("/api/resumes") && init && init.method === "POST") { failed = true; return Promise.reject(new TypeError("offline")); }
    return realFetch(url, init);
  };
  await b.chooseFiles("#resumeFile", [file("rahul.pdf")]);
  assert.match(b.text("#fileList"), /Cannot reach the server/);
  assert.equal(b.text("#fileCount"), "0");
  await b.click("[data-retry]");
  assert.deepEqual(names(b), ["rahul.pdf"]);
  assert.equal((await b.api("GET", "/api/resumes")).body.resumes.length, 1);
  b.close();
});

test("delete one resume and delete all", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  await b.chooseFiles("#resumeFile", [file("rahul.pdf"), file("priya.docx")]);
  await b.click("[data-delete]");
  assert.equal(b.text("#fileCount"), "1");
  await b.open("/upload.html");
  assert.equal(b.text("#fileCount"), "1");
  await b.click("#clearButton");
  assert.equal(b.text("#fileCount"), "0");
  assert.equal((await b.api("GET", "/api/resumes")).body.resumes.length, 0);
  b.close();
});

test("get started validates input, then saves the job setup", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/upload.html");
  await b.click("#startButton");
  assert.match(b.text("#pageMessage"), /upload at least one resume/i);

  await b.chooseFiles("#resumeFile", [file("rahul.pdf")]);
  await b.click("#startButton");
  assert.match(b.text("#pageMessage"), /at least one required skill/i);

  b.fill("#requiredSkills", "Python\nSQL, python\nGit");
  assert.match(b.text("#skillsPreview"), /3 skill/);
  b.fill("#jobTitle", "Backend Dev");
  b.fill("#jobDescription", "Build APIs with Python and SQL.");
  await b.click("#startButton");
  assert.match(b.text("#pageMessage"), /Analysis finished/);
  const jobs = (await b.api("GET", "/api/jobs")).body.jobs;
  assert.equal(jobs.length, 1);
  assert.deepEqual(jobs[0].required_skills, ["Python", "SQL", "Git"]);
  assert.equal(jobs[0].title, "Backend Dev");
  b.close();
});

test("another account never sees my resumes", async () => {
  const { browser: a } = await signedInBrowser();
  await a.open("/upload.html");
  await a.chooseFiles("#resumeFile", [file("rahul.pdf")]);
  const { browser: other } = await signedInBrowser();
  await other.open("/upload.html");
  assert.equal(other.text("#fileCount"), "0");
  const mine = (await a.api("GET", "/api/resumes")).body.resumes[0].id;
  assert.equal((await other.api("GET", `/api/resumes/${mine}`)).status, 404);
  a.close(); other.close();
});
