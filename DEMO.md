# Repeatable demo (about 5 minutes)

Everything here is real: nothing is mocked and nothing is pre-scored. The numbers below are asserted by
`tests/test_phase7_ops.py`, so if scoring ever changes this file must change with it.

## 1. Prepare
```bash
flask --app app db upgrade
flask --app app demo            # creates login "demo" + writes ./demo_resumes/
flask --app app run             # http://127.0.0.1:5000
```
`demo` prints the login (`demo` / `Demo-Pass-123`). It refuses to run when `APP_ENV=production`.

## 2. Walk through
1. Open http://127.0.0.1:5000 and sign in as **demo**. (Or click *Create Account* to show the two-step sign-up.)
2. **Upload Resumes** -> choose all five files in `demo_resumes/` (PDF and DOCX).
   They stay listed after a page refresh (saved on the server).
3. Required skills: `Python`, `SQL`, `Docker`, `AWS`, `React` (one per line).
   Job title: `Full-Stack Developer`. Job description: paste the text printed by the `demo` command
   (also in `riq/demo.py`).
4. **Get Started**. Each resume is analyzed and shown with its result.
5. Open **Results**, click a name to see skills found/missing, strengths, weaknesses and
   the *How this score was calculated* table. Try search, the status filter and sorting.

## 3. Expected results
| Resume | Result | Why |
|---|---|---|
| `anita_rao.docx` | **91.76** | all 5 skills (70 pts) + 58.8% of job keywords (11.76) + complete resume (10) |
| `vikram_shah.pdf` | **54.35** | Python, SQL, Docker = 3/5 skills (42) + keywords (2.35) + complete (10) |
| `meera_iyer.docx` | **26.35** | only React = 1/5 skills (14) + keywords (2.35) + complete (10) |
| `rohan_das.docx` | **7.84** | no required skills (0) + keywords (1.18) + no phone/projects (6.67) |
| `scanned_resume.pdf` | **Unsupported - no score** | image-only PDF; OCR is not supported, so nothing is invented |

## 4. Show the safety behaviour (optional)
- Upload `notes.txt` or a renamed file -> clear error, nothing saved. Upload the same file twice -> "already uploaded".
- Log out, then open `/ats-score.html` -> sent to login. Sign in again -> results are still there.
- Sign in as a second company: it sees none of the first company's resumes or results.

## Reset
Delete the demo account's data from the *Upload* page (Delete All Resumes) and delete runs on the *Results* page,
or drop and recreate the database and re-run `flask --app app db upgrade`.
