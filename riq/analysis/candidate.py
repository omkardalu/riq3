"""Rule-based extraction of contact details and sections from resume text (no ML, no guessing)."""
from __future__ import annotations

import re

from .normalize import normalize_lines

EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w])(?:\+?\d{1,3}[\s\-.]?)?(?:\(?\d{2,5}\)?[\s\-.]?)?\d{3,5}[\s\-.]?\d{3,5}(?![\w])")

SECTION_HEADINGS = {
    "education": {"education", "academic background", "academics", "qualifications", "academic qualifications",
                  "education and training", "educational qualifications"},
    "experience": {"experience", "work experience", "professional experience", "employment history", "work history",
                   "internships", "internship experience", "internship", "career history", "employment"},
    "projects": {"projects", "personal projects", "academic projects", "key projects", "project work", "selected projects"},
    "skills": {"skills", "technical skills", "key skills", "core competencies", "skills and tools", "skills summary",
               "technical proficiency", "technologies", "tech stack"},
    "summary": {"summary", "profile", "objective", "career objective", "about me", "professional summary", "profile summary"},
}
OTHER_HEADINGS = {"certifications", "certification", "achievements", "awards", "languages", "interests", "hobbies",
                  "references", "publications", "extracurricular activities", "personal details", "declaration",
                  "volunteering", "courses", "training"}
_NOT_NAMES = {"resume", "curriculum", "vitae", "cv", "profile", "summary", "contact", "address", "email", "phone"}
MAX_SECTION_LINES = 8
MAX_LINE_CHARS = 220


def _heading_key(line: str) -> str | None:
    key = re.sub(r"[^a-z& ]", "", line.replace("&", " and ")).strip()
    key = re.sub(r"\s+", " ", key)
    if not key or len(key) > 40:
        return None
    for name, words in SECTION_HEADINGS.items():
        if key in words:
            return name
    return "other" if key in OTHER_HEADINGS else None


def split_sections(text: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in normalize_lines(text).split("\n"):
        if not line:
            continue
        head = _heading_key(line.rstrip(":"))
        if head:
            current = head
            sections.setdefault(head, [])
            continue
        if current:
            sections[current].append(line)
    return sections


def find_email(text: str) -> str | None:
    m = EMAIL_RE.search(normalize_lines(text))
    return m.group(0) if m else None


def find_phone(text: str) -> str | None:
    for m in PHONE_RE.finditer(normalize_lines(text)):
        raw = m.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        if 10 <= len(digits) <= 13:
            return raw
    return None


def guess_name(original_text: str) -> str | None:
    """First of the first few lines that looks like a person's name (2-4 alphabetic words)."""
    seen = 0
    for line in original_text.splitlines():
        line = line.strip()
        if not line:
            continue
        seen += 1
        if seen > 6:
            break
        if "@" in line or any(ch.isdigit() for ch in line) or len(line) > 40:
            continue
        words = line.replace(",", " ").split()
        if not 2 <= len(words) <= 4:
            continue
        if any(not re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words):
            continue
        if {w.lower().strip(".") for w in words} & _NOT_NAMES or _heading_key(line.lower()):
            continue
        return line.title() if line.isupper() or line.islower() else line
    return None


def section_preview(lines: list[str]) -> list[str]:
    return [ln[:MAX_LINE_CHARS] for ln in lines[:MAX_SECTION_LINES]]


def parse_candidate(text: str, filename: str) -> dict:
    sections = split_sections(text)
    name = guess_name(text)
    source = "resume"
    if not name:
        stem = re.sub(r"[_\-.]+", " ", filename.rsplit(".", 1)[0]).strip()
        name, source = (stem.title() or "Unknown candidate"), "filename"
    return {
        "name": name,
        "name_source": source,
        "email": find_email(text),
        "phone": find_phone(text),
        "education": section_preview(sections.get("education", [])),
        "experience": section_preview(sections.get("experience", [])),
        "projects": section_preview(sections.get("projects", [])),
        "sections_found": sorted(k for k in sections if k in ("education", "experience", "projects", "skills", "summary")),
    }
