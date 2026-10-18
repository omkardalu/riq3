"""Deterministic text normalisation shared by every analysis step."""
from __future__ import annotations

import re
import unicodedata

_TRANSLATE = {
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2212": "-", "\u2010": "-", "\u2011": "-",
    "\u00a0": " ", "\u2022": " ", "\u25cf": " ", "\u25aa": " ", "\u25e6": " ", "\u2023": " ",
    "\u2192": " ", "\u00b7": " ", "\uf0b7": " ", "\u200b": "", "\u200c": "", "\u200d": "", "\ufeff": "", "\u00ad": "",
}
_TABLE = str.maketrans(_TRANSLATE)
_SPACES = re.compile(r"[ \t\f\v]+")


def normalize_lines(text: str) -> str:
    """Unicode-fold, lowercase, unify punctuation, collapse spaces - but keep line breaks."""
    text = unicodedata.normalize("NFKC", text or "").translate(_TABLE).lower()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = (_SPACES.sub(" ", ln).strip() for ln in text.split("\n"))
    return "\n".join(lines)


def normalize_flat(text: str) -> str:
    """Single-line form used for term matching."""
    return re.sub(r"\s+", " ", normalize_lines(text)).strip()
