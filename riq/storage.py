"""Private resume storage: files live outside the web root under UPLOAD_FOLDER/<user_id>/<uuid>.<ext>.

File names on disk are random UUIDs, never derived from user input, and are only
reachable through authenticated, ownership-checked API routes.
"""
from __future__ import annotations

import hashlib
import io
import os
import re
import uuid
import zipfile
from pathlib import Path

from flask import current_app

PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"
MAX_DOCX_UNCOMPRESSED = 100 * 1024 * 1024  # zip-bomb guard


def user_dir(user_id: int) -> Path:
    d = Path(current_app.config["UPLOAD_FOLDER"]) / str(user_id)
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    return d


def path_for(user_id: int, stored_name: str, ext: str) -> Path:
    return user_dir(user_id) / f"{stored_name}.{ext}"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_display_name(raw: str) -> str:
    """Display-only name: strip any path and control characters, cap length."""
    name = re.split(r"[\\/]", raw or "")[-1]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()
    return (name or "resume")[:255]


def sniff_type(data: bytes, ext: str) -> str | None:
    """Return None when the content matches the extension, else a human-readable problem."""
    if ext == "pdf":
        return None if data.lstrip(b"\x00\r\n ")[:5] == PDF_MAGIC else "This file is not a valid PDF."
    if ext == "docx":
        if data[:4] != ZIP_MAGIC:
            return "This file is not a valid DOCX document."
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                if "word/document.xml" not in names:
                    return "This file is not a valid DOCX document."
                if sum(i.file_size for i in z.infolist()) > MAX_DOCX_UNCOMPRESSED:
                    return "This DOCX file is too large once unpacked."
        except zipfile.BadZipFile:
            return "This file is not a valid DOCX document."
        return None
    return "Unsupported file type."


def save_bytes(user_id: int, ext: str, data: bytes) -> str:
    stored = uuid.uuid4().hex
    target = path_for(user_id, stored, ext)
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(data)
    os.chmod(tmp, 0o600)  # owner-only
    os.replace(tmp, target)  # atomic: no half-written resume is ever visible
    return stored


def delete_file(user_id: int, stored_name: str, ext: str) -> None:
    try:
        path_for(user_id, stored_name, ext).unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("could not delete stored file %s", stored_name)
