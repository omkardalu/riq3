"""Small, explicit input validation helpers (no hidden magic)."""
from __future__ import annotations

import re
from typing import Any

from flask import request

from .errors import ApiError

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,29}$")
PHONE_RE = re.compile(r"^[0-9+()\-.\s]{7,25}$")

INDUSTRIES = (
    "IT", "Software", "Finance", "Healthcare", "Education",
    "Manufacturing", "Retail", "Telecommunications", "Other",
)

PASSWORD_MIN, PASSWORD_MAX = 8, 128


def json_body() -> dict:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_json", "Request body must be a JSON object.")
    return data


def text(data: dict, key: str) -> str:
    value = data.get(key, "")
    return value.strip() if isinstance(value, str) else ""


def raise_if(errors: dict[str, str]) -> None:
    if errors:
        raise ApiError(422, "validation_error", "Please correct the highlighted fields.", errors)


def normalize_username(raw: str) -> str:
    return raw.strip().lstrip("@").lower()


def validate_password(password: Any, errors: dict[str, str], key: str = "password", username: str = "") -> None:
    if not isinstance(password, str) or not password:
        errors[key] = "Please enter a password."
    elif len(password) < PASSWORD_MIN:
        errors[key] = f"Password must be at least {PASSWORD_MIN} characters."
    elif len(password) > PASSWORD_MAX:
        errors[key] = f"Password must be at most {PASSWORD_MAX} characters."
    elif username and password.lower() == username.lower():
        errors[key] = "Password must not be the same as the username."


def validate_account_fields(data: dict) -> tuple[dict, dict[str, str]]:
    """Validate/normalise the company + identity fields shared by register and edit-profile."""
    errors: dict[str, str] = {}
    company = text(data, "company_name")
    email = text(data, "email").lower()
    phone = text(data, "phone")
    address = text(data, "address")
    industry = text(data, "industry")
    username = normalize_username(text(data, "username"))

    if not 2 <= len(company) <= 120:
        errors["company_name"] = "Company name must be 2-120 characters."
    if not email:
        errors["email"] = "Please enter an email address."
    elif len(email) > 254 or not EMAIL_RE.match(email):
        errors["email"] = "Please enter a valid email address."
    if not phone:
        errors["phone"] = "Please enter a phone number."
    elif not PHONE_RE.match(phone) or sum(c.isdigit() for c in phone) < 7:
        errors["phone"] = "Please enter a valid phone number."
    if address and len(address) > 500:
        errors["address"] = "Address must be at most 500 characters."
    if industry and industry not in INDUSTRIES:
        errors["industry"] = "Please choose an industry from the list."
    if not username:
        errors["username"] = "Please enter a username."
    elif not USERNAME_RE.match(username):
        errors["username"] = "Username must be 3-30 characters: letters, numbers, dot, dash or underscore."

    clean = {
        "company_name": company, "email": email, "phone": phone,
        "address": address, "industry": industry, "username": username,
    }
    return clean, errors
