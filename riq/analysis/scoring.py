"""Scoring v1 - documented in SCORING.md. Every number is traceable to a component below.

score = 100 * sum(weight_i * coverage_i)

  component        weight (with JD terms)   weight (no JD terms)
  required skills        0.70                    0.90
  JD keywords            0.20                    0.00
  resume structure       0.10                    0.10

coverage_skills     = matched required skills / required skills
coverage_jd         = summed weight of JD keywords found in the resume / summed weight of all JD keywords
coverage_structure  = signals present / 6   (email, phone, experience, education, skills, projects)
"""
from __future__ import annotations

from .candidate import parse_candidate, split_sections
from .skills import jd_keywords, match_jd_terms, match_skills

SCORING_VERSION = "v1"
WEIGHTS_WITH_JD = {"skills": 0.70, "jd_keywords": 0.20, "structure": 0.10}
WEIGHTS_NO_JD = {"skills": 0.90, "jd_keywords": 0.0, "structure": 0.10}
LABELS = {"skills": "Required skills", "jd_keywords": "Job description keywords", "structure": "Resume completeness"}


def _pct(x: float) -> float:
    return round(x * 100, 2)


def analyze_text(resume_text: str, filename: str, required_skills: list[str], job_description: str) -> dict:
    """Pure function: identical inputs always give identical output."""
    skill_results = match_skills(resume_text, required_skills)
    matched = [r for r in skill_results if r["matched"]]
    missing = [r["skill"] for r in skill_results if not r["matched"]]
    skill_cov = len(matched) / len(required_skills) if required_skills else 0.0

    terms = match_jd_terms(resume_text, jd_keywords(job_description, required_skills))
    total_w = sum(t["weight"] for t in terms)
    jd_cov = (sum(t["weight"] for t in terms if t["matched"]) / total_w) if total_w else 0.0
    weights = WEIGHTS_WITH_JD if terms else WEIGHTS_NO_JD

    candidate = parse_candidate(resume_text, filename)
    sections = set(candidate["sections_found"])
    signals = {
        "email": bool(candidate["email"]), "phone": bool(candidate["phone"]),
        "experience": "experience" in sections, "education": "education" in sections,
        "skills": "skills" in sections, "projects": "projects" in sections,
    }
    structure_cov = sum(signals.values()) / len(signals)

    coverage = {"skills": skill_cov, "jd_keywords": jd_cov if terms else 0.0, "structure": structure_cov}
    components = []
    score = 0.0
    for key in ("skills", "jd_keywords", "structure"):
        w = weights[key]
        if w == 0:
            continue
        points = w * coverage[key] * 100
        score += points
        components.append({"key": key, "label": LABELS[key], "weight": w, "coverage": _pct(coverage[key]), "points": round(points, 2)})
    score = round(score, 2)

    strengths, weaknesses, recs = _narrative(skill_results, matched, missing, skill_cov, terms, jd_cov, signals, score, len(required_skills))
    return {
        "score": score,
        "matched_percentage": _pct(skill_cov),
        "matched_skills": [r["skill"] for r in matched],
        "missing_skills": missing,
        "details": {
            "candidate": candidate,
            "components": components,
            "skill_matches": skill_results,
            "jd_terms": terms,
            "structure_signals": signals,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "recommendations": recs,
            "explanation": explain(components, len(matched), len(required_skills), score),
        },
    }


def explain(components: list[dict], n_matched: int, n_required: int, score: float) -> str:
    parts = [f"{c['label']}: {c['coverage']:g}% x weight {int(c['weight'] * 100)}% = {c['points']:g} points" for c in components]
    return f"Score {score:g}/100 = " + "; ".join(parts) + f". ({n_matched} of {n_required} required skills found.)"


def _join(items: list[str], limit: int = 6) -> str:
    shown = items[:limit]
    more = len(items) - len(shown)
    return ", ".join(shown) + (f" and {more} more" if more > 0 else "")


def _narrative(skill_results, matched, missing, skill_cov, terms, jd_cov, signals, score, n_required):
    strengths, weaknesses, recs = [], [], []
    if matched:
        strengths.append(f"Found {len(matched)} of {n_required} required skills: {_join([r['skill'] for r in matched])}.")
    heavy = [r["skill"] for r in matched if r["mentions"] >= 3]
    if heavy:
        strengths.append(f"Skills mentioned repeatedly (3+ times): {_join(heavy)}.")
    if terms and jd_cov >= 0.6:
        strengths.append("Resume wording closely follows the job description.")
    if signals["experience"] and signals["education"] and signals["skills"]:
        strengths.append("Clear Experience, Education and Skills sections.")

    if missing:
        weaknesses.append(f"Required skills not found: {_join(missing)}.")
    if terms and jd_cov < 0.4:
        weaknesses.append("Uses few of the job description's key terms.")
    absent = [k for k in ("experience", "education", "skills", "projects") if not signals[k]]
    if absent:
        weaknesses.append(f"No clearly labelled section for: {_join(absent)}.")
    if not signals["email"] or not signals["phone"]:
        weaknesses.append("Contact details incomplete (" + _join([k for k in ("email", "phone") if not signals[k]]) + " not found).")

    if score >= 75:
        recs.append("Strong match against the listed requirements: consider shortlisting.")
    elif score >= 50:
        recs.append("Partial match: review the resume manually before deciding.")
    else:
        recs.append("Weak match against the listed requirements.")
    if missing:
        recs.append(f"Ask about hands-on experience with: {_join(missing, 5)}.")
    return strengths, weaknesses, recs
