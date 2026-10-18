import { Browser } from "./browser.mjs";

export const BASE = process.env.BASE_URL || "http://127.0.0.1:5000";
let counter = 0;
export const uniq = (p = "u") => `${p}${Date.now().toString(36)}${(counter++).toString(36)}`;
export const PASSWORD = "correct-horse-1";

export function newBrowser() { return new Browser(BASE); }

/** Register through the real two-step UI. Returns {browser, username}. */
export async function registerViaUI(b = newBrowser(), over = {}) {
  const username = over.username || uniq("co");
  await b.open("/create-account.html");
  b.fill("#companyName", over.company || "ABC Technologies");
  b.fill("#companyEmail", over.email || `${username}@example.com`);
  b.fill("#companyPhone", "+91 98765 43210");
  b.fill("#companyAddress", "12 MG Road, Hyderabad");
  b.fill("#industry", "Software");
  await b.submit("#companyForm");
  if (b.path !== "/register.html") throw new Error("expected register.html, got " + b.path);
  b.fill("#username", username);
  b.fill("#password", over.password || PASSWORD);
  b.fill("#confirmPassword", over.password || PASSWORD);
  await b.submit("#registerForm");
  return { browser: b, username };
}

/** Fast path: sign up through the API inside a browser session. */
export async function signedInBrowser(over = {}) {
  const b = newBrowser();
  await b.open("/login.html");
  const username = over.username || uniq("co");
  const r = await b.api("POST", "/api/auth/register", {
    company_name: over.company || "ABC Technologies", email: `${username}@example.com`, phone: "+91 98765 43210",
    address: "12 MG Road, Hyderabad", industry: "Software", username, password: PASSWORD, confirm_password: PASSWORD,
  });
  if (r.status !== 201) throw new Error("register failed " + JSON.stringify(r));
  return { browser: b, username };
}
