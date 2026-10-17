Phase 0 — Stabilize the existing project
First

Goal: a clean, predictable starting point.
- Inspect all 12 existing files and map navigation.
- Fix broken links, casing, stray Markdown, duplicate listeners and empty links.
- Resolve the registration-page duplication and standardize filenames safely.
- Preserve the existing visual design and working interactions.
- Add a baseline test/checklist and Git checkpoint.
  Exit: every page loads and every navigation link works.




Phase 1 — Backend and database foundation
Goal: make the application capable of storing real data.
- Set up Flask with a clean application structure and configuration.
- Connect PostgreSQL using environment variables.
- Add database migrations and models for users, resumes, job descriptions and analyses.
- Create health-check and error-handling endpoints.
- Configure local development, dependencies and startup instructions.
  Exit: the API starts, connects to PostgreSQL and passes database CRUD tests.




Phase 2 — Authentication and user profiles
Goal: real accounts, not pretend login screens.
- Register, login, logout and session persistence.
- Hash passwords securely; never store plaintext passwords.
- Protect private API routes and enforce user ownership.
- Connect Profile, Edit Profile and Change Password to the backend.
- Provide validation, duplicate-email handling and understandable errors.
  Exit: a user can sign in, edit their profile, sign out and cannot access another user's data.




Phase 3 — Resume upload and job setup
Goal: real files move through the system safely.
- Upload PDF/DOCX resumes, with file size and type limits.
- Enter required skills and a job description.
- Validate duplicate files and invalid inputs.
- Store files privately and persist their metadata.
- Add upload status, loading states, retries where safe and clear errors.
  Exit: an authenticated user uploads a resume, refreshes the page and can still see their saved resume.




Phase 4 — Real resume analysis engine
Goal: produce reproducible, explainable results.
- Extract text from supported PDF and DOCX files.
- Normalize text, whitespace, punctuation and case.
- Match required skills and job-description terms against resume text.
- Calculate matched/missing skills and a documented weighted score.
- Persist analysis results, scoring version and processing status.
- Handle scanned PDFs, empty files and extraction failures honestly.
  Exit: identical inputs produce consistent results, and every score has an explanation. Scanned PDFs are reported as unsupported until OCR is deliberately added.




Phase 5 — ATS results and analysis history
Goal: close the upload-to-results loop.
- Replace the eight fake applicants with real API-driven data.
- Display score, matched skills, missing skills and recommendations.
- Add loading, empty, error and success states.
- Persist results and show analysis history.
- Add search, filtering and sorting only where they match the actual data model.
  Exit: uploading a resume and running analysis produces results that appear on the ATS Score page after refresh.




Phase 6 — UX and product consistency
Goal: make the whole product feel like one application.
- Apply consistent typography, colors, spacing and buttons.
- Fix desktop/mobile navigation and outside-click behavior.
- Improve skill badges, accessibility, form feedback and responsive layouts.
- Complete Features, How It Works, FAQs and footer navigation.
- Add favicon, page titles and sensible empty states.
  Exit: every page works across desktop and mobile without regressing functionality.




Phase 7 — Security, testing and submission
Goal: prove the complete flow works.
- Test registration, login, uploads, analysis, results and profile updates end to end.
- Test invalid files, expired sessions, database failures and unauthorized access.
- Review file storage, secrets, session cookies, CSRF protections and upload limits.
- Check logs, production configuration, deployment and database migrations.
- Run regression tests against every previously completed phase.
  Exit: a clean setup and repeatable demo work using documented instructions, with no fake success states.