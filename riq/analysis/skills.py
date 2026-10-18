"""Skill and keyword matching. Pure functions, no randomness: same input -> same output."""
from __future__ import annotations

import re
from functools import lru_cache

from .normalize import normalize_flat

# Groups of spellings that mean the same skill. Matching any member counts as a match for all.
ALIAS_GROUPS: list[tuple[str, ...]] = [
    ("javascript", "js", "ecmascript", "es6"),
    ("typescript", "ts"),
    ("node.js", "nodejs", "node js", "node"),
    ("react", "react.js", "reactjs", "react js"),
    ("vue.js", "vue", "vuejs"),
    ("angular", "angularjs", "angular.js"),
    ("next.js", "nextjs", "next js"),
    ("express", "express.js", "expressjs"),
    ("postgresql", "postgres", "psql"),
    ("mongodb", "mongo", "mongo db"),
    ("kubernetes", "k8s"),
    ("machine learning", "ml"),
    ("artificial intelligence", "ai"),
    ("natural language processing", "nlp"),
    ("c++", "cpp"),
    ("c#", "csharp", "c sharp"),
    (".net", "dotnet", "dot net"),
    ("aws", "amazon web services"),
    ("gcp", "google cloud platform", "google cloud"),
    ("azure", "microsoft azure"),
    ("ci/cd", "ci cd", "cicd", "ci-cd", "continuous integration"),
    ("rest api", "rest apis", "restful api", "restful apis", "rest", "restful"),
    ("html", "html5"),
    ("css", "css3"),
    ("git", "github", "gitlab"),
    ("problem solving", "problem-solving"),
    ("communication", "communication skills"),
]
_ALIAS_INDEX: dict[str, tuple[str, ...]] = {}
for _g in ALIAS_GROUPS:
    for _m in _g:
        _ALIAS_INDEX[_m] = _g

# A skill may not be glued to other letters/digits/+/#, nor continue as ".word" (so "java" != "javascript",
# "c" != "c++" / "c#", "react" != "react.js" - the latter is covered by aliases).
_PRE = r"(?<![a-z0-9+#])(?<![a-z0-9]\.)"
_POST = r"(?![a-z0-9+#])(?!\.[a-z0-9])"


def variants(skill: str) -> list[str]:
    """All normalised spellings to look for, most specific first (deterministic order)."""
    base = normalize_flat(skill)
    out: list[str] = []

    def add(v: str):
        v = v.strip()
        if v and v not in out:
            out.append(v)

    add(base)
    for member in _ALIAS_INDEX.get(base, ()):
        add(member)
    # punctuation variants: "node.js" -> "nodejs", "node js"; "ci/cd" -> "ci cd"
    for v in list(out):
        add(v.replace(".", ""))
        add(v.replace(".", " "))
        add(v.replace("-", " "))
        add(v.replace("/", " "))
    return out


@lru_cache(maxsize=4096)
def _pattern(variant: str) -> re.Pattern:
    body = r"\s+".join(re.escape(part) for part in variant.split(" "))
    return re.compile(_PRE + body + _POST)


def count_mentions(flat_text: str, variant: str) -> int:
    return len(_pattern(variant).findall(flat_text))


def match_skill(flat_text: str, skill: str) -> dict:
    """{skill, matched, matched_as, mentions} for one required skill."""
    best, first = 0, None
    for v in variants(skill):
        n = count_mentions(flat_text, v)
        if n:
            first = first or v
            best = max(best, n)  # aliases overlap ("rest api" / "rest"), so take the largest single spelling
    return {"skill": skill, "matched": best > 0, "matched_as": first, "mentions": best}


def match_skills(resume_text: str, skills: list[str]) -> list[dict]:
    flat = normalize_flat(resume_text)
    return [match_skill(flat, s) for s in skills]


# ---------------- job-description keywords ----------------

STOPWORDS = frozenset("""
a about above across after again against all also am an and any are as at be because been before being below between both but by can
could did do does doing down during each either else etc even ever every few for from further had has have having he her here hers him his
how i if in into is it its just like may me might more most must my no nor not now of off on once only or other our out over own per same
shall she should so some such than that the their them then there these they this those through to too under until up us use used using very
was we were what when where which while who whom why will with within without would you your yours
experience experienced work working works team teams years year ability able strong strongly knowledge skills skill looking role roles
candidate candidates responsibilities responsibility requirements requirement required preferred plus including include includes good great
excellent proven demonstrated job description position company opportunity join help helping build building ensure ensuring across
understanding understand familiar familiarity hands-on handson related relevant new existing high quality level well best based
minimum degree bachelor bachelors master masters equivalent applicants apply need needs needed seeking
""".split())

_TOKEN = re.compile(r"[a-z][a-z0-9+#]*(?:[.\-/][a-z0-9+#]+)*")
MAX_JD_TERMS = 25


def _tokens(flat: str) -> list[str]:
    return _TOKEN.findall(flat)


def jd_keywords(description: str, skills: list[str]) -> list[dict]:
    """Most frequent meaningful terms of the job description (excluding the required skills).

    Unigrams need >= 1 mention, bigrams >= 2 (to avoid noise). Ranked by frequency, then alphabetically,
    so the list is identical for identical input.
    """
    flat = normalize_flat(description)
    if not flat:
        return []
    skill_forms = {v for s in skills for v in variants(s)}
    skill_words = {w for f in skill_forms for w in re.split(r"[\s.\-/]+", f) if w}
    toks = _tokens(flat)
    counts: dict[str, int] = {}
    for i, t in enumerate(toks):
        if t in STOPWORDS or len(t) < 3 or t in skill_forms:
            continue
        counts[t] = counts.get(t, 0) + 1
    for a, b in zip(toks, toks[1:]):
        if a in STOPWORDS or b in STOPWORDS or len(a) < 3 or len(b) < 3:
            continue
        bg = f"{a} {b}"
        if bg in skill_forms:
            continue
        counts[bg] = counts.get(bg, 0) + 1
    terms = []
    for term, n in counts.items():
        is_bigram = " " in term
        if is_bigram and n < 2:
            continue
        if not is_bigram and term in skill_words:
            continue
        terms.append((term, n))
    # drop unigrams fully covered by a kept bigram of equal frequency (keeps list compact)
    terms.sort(key=lambda x: (-x[1], x[0]))
    return [{"term": t, "weight": n} for t, n in terms[:MAX_JD_TERMS]]


def match_jd_terms(resume_text: str, terms: list[dict]) -> list[dict]:
    flat = normalize_flat(resume_text)
    out = []
    for item in terms:
        body = r"\s+".join(re.escape(p) for p in item["term"].split(" "))
        pat = re.compile(_PRE + body + r"(?:s|es)?" + _POST)
        out.append({**item, "matched": bool(pat.search(flat))})
    return out
