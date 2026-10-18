# How Resume IQ scores a resume (scoring version `v1`)

Everything is rule-based and deterministic: identical resume text + identical job setup always produce the
identical score. There is no machine-learning model and no randomness. Every result stores its
`scoring_version`, a per-component breakdown and a plain-English explanation.

## 1. Reading the file
- **PDF:** text is read with `pypdf` (first 30 pages). **DOCX:** paragraphs and tables are read in document order.
- Fewer than 30 readable characters means there is no usable text:
  - a PDF is reported **unsupported (scanned image)** - there is no OCR yet, and no score is invented;
  - an empty DOCX is reported **failed**; damaged or password-protected files are reported **failed**.
- Extracted text is cached on the resume so re-analysis is instant and consistent.

## 2. Normalisation
Unicode NFKC, lower-case, smart quotes/dashes/bullets unified, zero-width characters removed, whitespace collapsed.

## 3. Matching required skills
A skill matches when it appears as a whole term. Boundaries are strict:
`Java` does **not** match `JavaScript`; `C` does not match `C++` or `C#`; `React` does not match `reactive`.
Known spellings count as the same skill (e.g. `JS`/`JavaScript`, `Node.js`/`nodejs`, `K8s`/`Kubernetes`,
`Postgres`/`PostgreSQL`, `CI/CD`) - see `ALIAS_GROUPS` in `riq/analysis/skills.py`.
`mentions` is the highest count of any single spelling.

## 4. Job-description keywords
The most frequent meaningful words of the job description (stop-words and the required skills removed;
single words need 1 mention, two-word phrases need 2; top 25; ties broken alphabetically).
A keyword is "found" if the resume contains it (simple plural allowed).

## 5. Resume completeness
Six signals: email, phone, Experience section, Education section, Skills section, Projects section
(section headings are recognised from a fixed list of common names).

## 6. The score
```
score = 100 x ( w_skills x skill_coverage + w_jd x jd_coverage + w_structure x structure_coverage )
```
| component | what is measured | weight with JD keywords | weight without |
|---|---|---|---|
| Required skills | matched skills / required skills | 70% | 90% |
| Job description keywords | weight of keywords found / total keyword weight | 20% | - |
| Resume completeness | signals present / 6 | 10% | 10% |

`matched_percentage` is the skill coverage; `unmatched_percentage` is `100 - matched_percentage`.

## 7. Strengths / weaknesses / recommendations
Generated from fixed rules over the numbers above (for example "Required skills not found: ...").
Score >= 75 suggests shortlisting, 50-74 manual review, below 50 a weak match. They are guidance, not a verdict.

## Known limits
No OCR (scanned PDFs are unsupported), no `.doc` files, no semantic understanding (a skill described in
other words will not match unless it is a listed alias), contact/name extraction is heuristic.
