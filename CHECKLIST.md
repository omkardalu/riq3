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
