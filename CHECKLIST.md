# Manual regression checklist

Run top to bottom after any change. Automated coverage lives in `tests/`.

## Navigation (Phase 0 baseline)
- [ ] `login.html` → "Create Account" opens `create-account.html`
- [ ] `create-account.html` (step 1) → NEXT opens `register.html` (step 2); "Login" opens `login.html`
- [ ] `register.html` → completing the form lands on `homepage.html`
- [ ] `homepage.html` → Features, How It Works, Upload Resume, menu → Profile / Logout
- [ ] `features.html` and `how-it-works.html` → back button works; START SCREENING opens `upload.html`
- [ ] `profile.html` → Edit Profile → `edit-profile.html`; Change Password → `change-password.html`
- [ ] `edit-profile.html` / `change-password.html` → Cancel returns to `profile.html`
- [ ] `upload.html` → "Upload More Resumes" from `ats-score.html` returns here
- [ ] Browser console shows no errors on any page

## Product flow (Phases 2-5)
- [ ] Register → logged in; logout → protected pages redirect to login
- [ ] Login with wrong password shows an error; right password works
- [ ] Edit profile persists after refresh; change password works and old password stops working
- [ ] Upload PDF + DOCX; refresh; both still listed
- [ ] Upload a duplicate / .txt / oversized file → clear error each time
- [ ] Analyze → results on `ats-score.html`; refresh → results still there
- [ ] A scanned (image-only) PDF is reported as unsupported, not scored

## Responsive / visual pass (Phase 6) - do this in a real browser
Automated tests verify structure (viewport tags, landmarks, links, ARIA state) but cannot see pixels.
Check each page at **360 px (phone)**, **768 px (tablet)** and **1280 px (desktop)**:
- [ ] No horizontal scrolling on any page (login box, tables on `ats-score.html`, FAQ, footer links)
- [ ] `homepage.html`: nav links wrap neatly, account menu opens/closes (tap outside, Esc), FAQ opens/closes, footer links wrap
- [ ] `features.html` / `how-it-works.html`: shared nav + footer, 3 -> 2 -> 1 feature columns
- [ ] `upload.html`: skill chips wrap, file rows do not overflow, result rows readable
- [ ] `ats-score.html`: toolbar stacks, table scrolls inside its card, detail cards stack to one column
- [ ] Keyboard only: Tab shows a visible focus ring everywhere; the "Skip to main content" link appears on first Tab
- [ ] Zoom to 200%: nothing is cut off
