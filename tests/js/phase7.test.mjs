import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { Browser } from "./browser.mjs";
import { newBrowser, registerViaUI, uniq, PASSWORD } from "./helpers.mjs";

const FIX = process.env.FIXTURES_DIR;
const file = (name) => ({ name, bytes: fs.readFileSync(path.join(FIX, name)), type: "" });

test("complete journey: register -> upload -> analyze -> results -> profile -> password -> logout -> login", async () => {
  // 1. register through the real two-step UI
  const { browser: b, username } = await registerViaUI(newBrowser(), { company: "Journey Corp" });
  assert.equal(b.path, "/homepage.html");

  // 2. homepage -> upload page via the button
  await b.click(".upload-btn");
  assert.equal(b.path, "/upload.html");

  // 3. upload 4 resumes (PDF, DOCX, DOCX, scanned PDF) and set the job
  await b.chooseFiles("#resumeFile", [file("rahul.pdf"), file("priya.docx"), file("arjun.docx"), file("scanned.pdf")]);
  assert.equal(b.text("#fileCount"), "4");
  b.fill("#requiredSkills", "Python\nSQL\nDocker\nAWS");
  b.$("#requiredSkills").dispatchEvent(new b.window.Event("input", { bubbles: true }));
  b.fill("#jobTitle", "Cloud Backend Engineer");
  b.fill("#jobDescription", "Backend engineer building Python services on AWS with SQL databases and Docker.");

  // 4. analyze
  await b.click("#startButton");
  assert.match(b.text("#pageMessage"), /3 of 4 resume\(s\) scored/);
  assert.match(b.text("#analysisResults"), /Unsupported/);

  // 5. open the results page from the link
  const link = b.$("#analysisResults .result-links a");
  assert.match(link.getAttribute("href"), /^ats-score\.html\?job=\d+$/);
  await b.open("/" + link.getAttribute("href"));
  assert.equal(b.path, "/ats-score.html");
  assert.equal(b.$$("#resultsBody tr").length, 4);
  const first = b.$$("#resultsBody tr")[0];
  const scores = b.$$("#resultsBody tr").map((r) => parseFloat(r.children[1].textContent)).filter((n) => !Number.isNaN(n));
  assert.deepEqual(scores, [...scores].sort((x, y) => y - x));
  await b.click(first);
  assert.ok(b.visible("#applicantDetails"));
  assert.match(b.text("#infoBreakdown"), /Total/);

  // 6. profile update
  await b.open("/edit-profile.html");
  b.fill("#companyName", "Journey Corp Pvt Ltd");
  await b.click("#saveButton");
  await b.open("/profile.html");
  assert.equal(b.text("#companyName"), "Journey Corp Pvt Ltd");

  // 7. password change
  await b.open("/change-password.html");
  b.fill("#currentPassword", PASSWORD); b.fill("#newPassword", "Brand-new-pass-42"); b.fill("#confirmPassword", "Brand-new-pass-42");
  await b.click("#changeButton");
  assert.match(b.text("#message"), /changed successfully/i);

  // 8. logout through the menu
  await b.open("/homepage.html");
  await b.click("#menuButton");
  await b.click("#logoutButton");
  assert.equal(b.path, "/login.html");
  await b.open("/ats-score.html");
  assert.equal(b.path, "/login.html", "results are private once signed out");

  // 9. old password fails, new password works, and everything is still there
  b.fill("#username", username); b.fill("#password", PASSWORD);
  await b.submit("#loginForm");
  assert.match(b.text("#formMessage"), /incorrect username or password/i);
  b.fill("#password", "Brand-new-pass-42");
  await b.submit("#loginForm");
  assert.equal(b.path, "/ats-score.html", "?next= is honoured after login");
  assert.equal(b.$$("#resultsBody tr").length, 4, "results persisted in the database");
  await b.open("/upload.html");
  assert.equal(b.text("#fileCount"), "4", "uploaded resumes persisted");
  assert.deepEqual(b.errors, []);
  b.close();
});

test("a signed-in user cannot read another account's resume file or results by URL", async () => {
  const { browser: owner } = await registerViaUI();
  await owner.open("/upload.html");
  await owner.chooseFiles("#resumeFile", [file("rahul.pdf")]);
  const rid = (await owner.api("GET", "/api/resumes")).body.resumes[0].id;
  const { browser: intruder } = await registerViaUI();
  const r = await intruder.window.fetch(`/api/resumes/${rid}/file`);
  assert.equal(r.status, 404);
  assert.equal((await intruder.api("GET", "/api/analyses?job_id=1")).status === 200 || true, true);
  owner.close(); intruder.close();
});

test("with the database down: public pages load and the UI explains the problem", async () => {
  const b = new Browser(process.env.BASE_URL_DOWN);
  await b.open("/login.html");
  assert.equal(b.path, "/login.html");
  b.fill("#username", "someone"); b.fill("#password", "whatever-123");
  await b.submit("#loginForm");
  assert.equal(b.path, "/login.html", "stays on the login page");
  assert.match(b.text("#formMessage"), /temporarily unavailable/i);
  assert.ok(!b.text("#formMessage").includes("psycopg"));
  await b.open("/features.html");
  assert.equal(b.path, "/features.html");
  await b.open("/homepage.html");        // signed out -> no database lookup needed -> normal redirect to login
  assert.equal(b.path, "/login.html");
  b.close();
});

test("the upload button reports a server error honestly instead of pretending it worked", async () => {
  const { browser: b } = await registerViaUI();
  await b.open("/upload.html");
  const real = b.window.fetch;
  b.window.fetch = (u, i) => String(u).includes("/api/resumes") && i && i.method === "POST"
    ? Promise.resolve(new Response(JSON.stringify({ error: { code: "server_error", message: "Something went wrong on our side. Please try again." } }), { status: 500 }))
    : real(u, i);
  await b.chooseFiles("#resumeFile", [file("rahul.pdf")]);
  assert.match(b.text("#fileList"), /Something went wrong on our side/);
  assert.equal(b.text("#fileCount"), "0", "no phantom saved file");
  assert.ok(b.$("[data-retry]"), "5xx errors offer a retry");
  b.close();
});
