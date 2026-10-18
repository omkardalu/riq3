"""Static audit of the HTML pages (stdlib only).

Used by tests/test_phase0_static.py and runnable directly:
    python tests/static_audit.py
Checks every page for: broken local links / redirects, filename casing,
stray Markdown, duplicate ids, getElementById() targets that do not exist,
duplicate addEventListener registrations and empty links.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def pages_dir() -> Path:
    for candidate in (ROOT / "web" / "pages", ROOT):
        if list(candidate.glob("*.html")):
            return candidate
    raise SystemExit("no html pages found")


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids: list[str] = []
        self.links: list[tuple[str, str]] = []  # (tag, target)
        self.scripts: list[str] = []
        self._in_script = False
        self._buf: list[str] = []
        self.empty_links: list[str] = []
        # accessibility bookkeeping
        self.html_lang = None
        self.has_viewport = False
        self.has_icon = False
        self.title = ""
        self._in_title = False
        self.imgs_without_alt: list[str] = []
        self.controls: list[dict] = []          # form controls needing a label
        self.label_for: set[str] = set()
        self._label_depth = 0
        self._named: list[dict] = []            # buttons / links needing an accessible name
        self._cur_named: dict | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.html_lang = a.get("lang")
        if tag == "meta" and a.get("name") == "viewport":
            self.has_viewport = True
        if tag == "link" and "icon" in (a.get("rel") or ""):
            self.has_icon = True
        if tag == "title":
            self._in_title = True
        if tag == "img" and "alt" not in a:
            self.imgs_without_alt.append(a.get("src", "?"))
        if tag == "label":
            self._label_depth += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        if tag in ("input", "select", "textarea") and a.get("type") not in ("hidden", "submit", "button", "reset", "image"):
            self.controls.append({"tag": tag, "id": a.get("id"), "type": a.get("type"),
                                  "named": bool(a.get("aria-label") or a.get("aria-labelledby") or a.get("title")),
                                  "in_label": self._label_depth > 0})
        if tag in ("button", "a") and not (tag == "a" and not a.get("href")):
            self._cur_named = {"tag": tag, "id": a.get("id") or a.get("href") or "?",
                               "named": bool(a.get("aria-label") or a.get("title")), "text": ""}
        if "id" in a:
            self.ids.append(a["id"])
        if tag == "a":
            href = a.get("href")
            if href is None or href.strip() in ("", "#"):
                self.empty_links.append(str(a))
            else:
                self.links.append((tag, href))
        if tag == "link" and a.get("href"):
            self.links.append((tag, a["href"]))
        if tag == "script":
            if a.get("src"):
                self.links.append((tag, a["src"]))
            self._in_script = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "label" and self._label_depth:
            self._label_depth -= 1
        if tag in ("button", "a") and self._cur_named is not None:
            self._named.append(self._cur_named)
            self._cur_named = None
        if tag == "script" and self._in_script:
            self.scripts.append("".join(self._buf))
            self._in_script = False

    def handle_data(self, data):
        if self._in_script:
            self._buf.append(data)
        if self._in_title:
            self.title += data
        if self._cur_named is not None:
            self._cur_named["text"] += data


EXTERNAL = re.compile(r"^(https?:)?//|^mailto:|^tel:|^javascript:|^data:|^#")
NAV_JS = re.compile(r"location(?:\.href)?\s*=\s*[\"']([^\"']+)[\"']")


def audit_page(path: Path, known: set[str]) -> list[str]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")
    c = _Collector()
    c.feed(text)
    name = path.name

    if name != name.lower() or " " in name:
        problems.append(f"{name}: filename must be lowercase without spaces")
    if "```" in text:
        problems.append(f"{name}: stray Markdown code fence")
    if "\r" in text:
        problems.append(f"{name}: CRLF line endings")

    for tag, target in c.links:
        if EXTERNAL.match(target):
            continue
        clean = target.split("#")[0].split("?")[0]
        if clean and not clean.startswith("/") and clean not in known:
            problems.append(f"{name}: broken <{tag}> target '{target}'")
    for target in NAV_JS.findall("\n".join(c.scripts)):
        clean = target.split("#")[0].split("?")[0]
        if EXTERNAL.match(target) or not clean or clean.startswith("/"):
            continue
        if clean not in known:
            problems.append(f"{name}: broken JS navigation target '{target}'")
    for el in c.empty_links:
        problems.append(f"{name}: empty link {el}")

    # ---- consistency + accessibility
    if not c.html_lang:
        problems.append(f"{name}: <html> needs a lang attribute")
    if not c.has_viewport:
        problems.append(f"{name}: missing viewport meta tag")
    if not c.has_icon:
        problems.append(f"{name}: missing favicon link")
    if not c.title.strip().startswith("Resume IQ"):
        problems.append(f"{name}: title should start with 'Resume IQ' (got {c.title.strip()!r})")
    for src in c.imgs_without_alt:
        problems.append(f"{name}: <img {src}> has no alt text")
    for ctl in c.controls:
        if not (ctl["named"] or ctl["in_label"] or (ctl["id"] and ctl["id"] in c.label_for)):
            problems.append(f"{name}: form control #{ctl['id']} ({ctl['tag']}) has no label")
    for el in c._named:
        if not (el["named"] or el["text"].strip()):
            problems.append(f"{name}: <{el['tag']} {el['id']}> has no accessible name")

    dup = [i for i, n in Counter(c.ids).items() if n > 1]
    for i in dup:
        problems.append(f"{name}: duplicate id '{i}'")

    js = "\n".join(c.scripts)
    for ident in set(re.findall(r"getElementById\(\s*[\"']([^\"']+)[\"']\s*\)", js)):
        if ident not in c.ids and f"id=\"{ident}\"" not in js and f"id='{ident}'" not in js:
            problems.append(f"{name}: getElementById('{ident}') has no element")

    listeners = re.findall(
        r"getElementById\(\s*[\"']([^\"']+)[\"']\s*\)\s*\.addEventListener\(\s*[\"'](\w+)[\"']", js
    )
    for (ident, ev), n in Counter(listeners).items():
        if n > 1:
            problems.append(f"{name}: {n} '{ev}' listeners on #{ident}")
    return problems


def audit() -> list[str]:
    base = pages_dir()
    files = sorted(base.glob("*.html"))
    known = {f.name for f in files}
    assets = ROOT / "web" / "assets"
    if assets.exists():
        known |= {str(p.relative_to(ROOT / "web")) for p in assets.rglob("*") if p.is_file()}
    out: list[str] = []
    for f in files:
        out += audit_page(f, known)
    return out


if __name__ == "__main__":
    probs = audit()
    print("\n".join(probs) if probs else "OK: no problems")
    sys.exit(1 if probs else 0)
