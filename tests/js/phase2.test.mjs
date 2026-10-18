import test from "node:test";
import assert from "node:assert/strict";
import { newBrowser, registerViaUI, signedInBrowser, uniq, PASSWORD } from "./helpers.mjs";
import { PAGES } from "./browser.mjs";

test("public pages load with a title and no script errors", async () => {
  for (const p of PAGES.public) {
    const b = newBrowser();
    await b.open(`/${p}.html`);
    // register.html is step 2: opened directly it correctly returns to step 1
    assert.equal(b.path, p === "register" ? "/create-account.html" : `/${p}.html`, p);
    assert.ok(b.document.title.trim().length > 0, `${p} has a title`);
    assert.deepEqual(b.errors, [], `${p} script errors`);
    b.close();
  }
});

test("protected pages send signed-out visitors to login with ?next=", async () => {
  for (const p of PAGES.protected) {
    const b = newBrowser();
    await b.open(`/${p}.html`);
    assert.equal(b.path, "/login.html", p);
    assert.equal(b.url.searchParams.get("next"), `/${p}.html`, p);
    b.close();
  }
});

test("every protected page loads for a signed-in user without script errors", async () => {
  const { browser: b } = await signedInBrowser();
  for (const p of PAGES.protected) {
    await b.open(`/${p}.html`);
    assert.equal(b.path, `/${p}.html`, p);
    assert.deepEqual(b.errors, [], `${p}: ${b.errors.join("; ")}`);
  }
  b.close();
});

test("registration: two steps, then lands signed-in on the homepage", async () => {
  const { browser: b, username } = await registerViaUI();
  assert.equal(b.path, "/homepage.html");
  const me = await b.api("GET", "/api/auth/me");
  assert.equal(me.body.user.username, username);
  assert.equal(me.body.user.company_name, "ABC Technologies");
  assert.deepEqual(b.errors, []);
  b.close();
});

test("registration: skipping step 1 bounces back to company details", async () => {
  const b = newBrowser();
  await b.open("/register.html");
  assert.equal(b.path, "/create-account.html");
  b.close();
});

test("registration: duplicate username is reported next to the field", async () => {
  const { browser: first, username } = await registerViaUI();
  first.close();
  const b = newBrowser();
  await registerViaUI(b, { username, email: `${uniq("other")}@example.com` });
  assert.equal(b.path, "/register.html");
  assert.match(b.text("#username ~ .riq-field-error, .input-box .riq-field-error") || "", /already taken/i);
  b.close();
});

test("registration: mismatched passwords are caught before any request", async () => {
  const b = newBrowser();
  await b.open("/create-account.html");
  b.fill("#companyName", "X Co"); b.fill("#companyEmail", `${uniq("m")}@example.com`);
  b.fill("#companyPhone", "+91 98765 43210"); b.fill("#companyAddress", "Somewhere 123"); b.fill("#industry", "IT");
  await b.submit("#companyForm");
  b.fill("#username", uniq("mm")); b.fill("#password", PASSWORD); b.fill("#confirmPassword", "different-pass-1");
  await b.submit("#registerForm");
  assert.equal(b.path, "/register.html");
  assert.ok(b.visible("#passwordError"));
  b.close();
});

test("login: wrong password shows an error, right password signs in and honours ?next=", async () => {
  const { browser: reg, username } = await registerViaUI();
  await reg.api("POST", "/api/auth/logout");
  reg.close();

  const b = newBrowser();
  await b.open("/login.html?next=/profile.html");
  b.fill("#username", username); b.fill("#password", "wrong-password-1");
  await b.submit("#loginForm");
  assert.equal(b.path, "/login.html");
  assert.match(b.text("#formMessage"), /incorrect username or password/i);

  b.fill("#password", PASSWORD);
  await b.submit("#loginForm");
  assert.equal(b.path, "/profile.html");
  assert.deepEqual(b.errors, []);
  b.close();
});

test("login: open-redirect attempts via ?next= are ignored", async () => {
  const { browser: reg, username } = await registerViaUI();
  await reg.api("POST", "/api/auth/logout");
  reg.close();
  const b = newBrowser();
  await b.open("/login.html?next=" + encodeURIComponent("https://evil.example/x.html"));
  b.fill("#username", username); b.fill("#password", PASSWORD);
  await b.submit("#loginForm");
  assert.equal(b.path, "/homepage.html");
  assert.equal(b.url.host, new URL(b.base).host);
  b.close();
});

test("logout from the menu ends the session", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/homepage.html");
  await b.click("#menuButton");
  assert.ok(b.visible("#dropdown"));
  await b.click("#logoutButton");
  assert.equal(b.path, "/login.html");
  await b.open("/profile.html");
  assert.equal(b.path, "/login.html");
  b.close();
});

test("menu closes on outside click and Escape", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/homepage.html");
  await b.click("#menuButton");
  assert.ok(b.visible("#dropdown"));
  b.document.body.click();
  assert.ok(!b.visible("#dropdown"));
  await b.click("#menuButton");
  b.document.dispatchEvent(new b.window.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  assert.ok(!b.visible("#dropdown"));
  b.close();
});

test("profile page shows the real account; edit profile persists changes", async () => {
  const { browser: b, username } = await signedInBrowser({ company: "Zeta Labs" });
  await b.open("/profile.html");
  assert.equal(b.text("#companyName"), "Zeta Labs");
  assert.equal(b.text("#usernameDetail"), "@" + username);
  assert.equal(b.text("#industry"), "Software");

  await b.click(".edit-btn");
  assert.equal(b.path, "/edit-profile.html");
  assert.equal(b.$("#companyName").value, "Zeta Labs");
  b.fill("#companyName", "Zeta Labs Pvt Ltd");
  b.fill("#phone", "+91 90000 11111");
  b.fill("#industry", "Finance");
  await b.click("#saveButton");
  assert.match(b.text("#message"), /updated successfully/i);
  await b.open("/profile.html");
  assert.equal(b.text("#companyName"), "Zeta Labs Pvt Ltd");
  assert.equal(b.text("#phone"), "+91 90000 11111");
  assert.equal(b.text("#industry"), "Finance");
  b.close();
});

test("edit profile: validation and duplicate errors appear next to the field", async () => {
  const { browser: other, username: taken } = await signedInBrowser();
  other.close();
  const { browser: b } = await signedInBrowser();
  await b.open("/edit-profile.html");
  b.fill("#email", "not-an-email");
  await b.click("#saveButton");
  assert.match(b.text(".form-group .riq-field-error"), /valid email/i);
  b.fill("#email", `${uniq("ok")}@example.com`);
  b.fill("#username", taken);
  await b.click("#saveButton");
  assert.match(b.$$(".riq-field-error").map((e) => e.textContent).join(" "), /already taken/i);
  b.close();
});

test("change password: wrong current, mismatch, then success; old password stops working", async () => {
  const { browser: b, username } = await signedInBrowser();
  await b.open("/change-password.html");
  b.fill("#currentPassword", "wrong-password-1"); b.fill("#newPassword", "brand-new-pass-1"); b.fill("#confirmPassword", "brand-new-pass-1");
  await b.click("#changeButton");
  assert.match(b.$$(".riq-field-error").map((e) => e.textContent).join(" "), /incorrect/i);

  b.fill("#currentPassword", PASSWORD); b.fill("#confirmPassword", "something-else-1");
  await b.click("#changeButton");
  assert.match(b.text(".riq-field-error"), /do not match/i);

  b.fill("#confirmPassword", "brand-new-pass-1");
  await b.click("#changeButton");
  assert.match(b.text("#message"), /changed successfully/i);

  await b.api("POST", "/api/auth/logout");
  assert.equal((await b.api("POST", "/api/auth/login", { username, password: PASSWORD })).status, 401);
  assert.equal((await b.api("POST", "/api/auth/login", { username, password: "brand-new-pass-1" })).status, 200);
  b.close();
});

test("an expired/invalid session on a protected page redirects to login with a notice", async () => {
  const { browser: b } = await signedInBrowser();
  await b.open("/profile.html");
  await b.api("POST", "/api/auth/logout");        // session dies behind the page's back
  await b.window.RIQ.api("/api/profile").catch(() => {});
  await b.settle();
  assert.equal(b.path, "/login.html");
  assert.equal(b.url.searchParams.get("expired"), "1");
  assert.match(b.text("#formMessage"), /session has expired/i);
  b.close();
});
