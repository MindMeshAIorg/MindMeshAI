import re


AUTH_MESSAGE_PATTERNS = [
    r"(?i)\blogin code\b",
    r"(?i)\bverification code\b",
    r"(?i)\bweb login code\b",
    r"(?i)\baccount recovery\b",
    r"(?i)\bdelete your (?:telegram )?account\b",
    r"(?i)\bdo not give this code to anyone\b",
]

REDACTION_PATTERNS = [
    # OTPs with common labels
    (
        r"(?i)\b(?:otp|verification code|login code|security code)"
        r"\s*(?:is|:|=)?\s*[\w-]{4,12}\b",
        "[REDACTED_AUTH_CODE]",
    ),
    # Email addresses
    (
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[REDACTED_EMAIL]",
    ),
    # Indian phone numbers
    (
        r"(?<!\d)(?:\+91[\s-]?)?[6-9]\d{9}(?!\d)",
        "[REDACTED_PHONE]",
    ),
    # Bearer tokens
    (
        r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+",
        "Bearer [REDACTED_TOKEN]",
    ),
    # Explicitly labelled passwords
    (
        r"(?i)\b(password|passwd|pwd)\s*[:=]\s*\S+",
        r"\1=[REDACTED_PASSWORD]",
    ),
]


def is_auth_message(record: dict) -> bool:
    """Identify messages that should not enter the database."""
    text = record.get("text") or ""
    sender = (record.get("sender") or "").strip().lower()
    subject = record.get("subject") or ""

    # Telegram's official service account
    if record.get("source") == "telegram" and sender == "telegram":
        return True

    content = f"{subject}\n{text}"
    return any(
        re.search(pattern, content)
        for pattern in AUTH_MESSAGE_PATTERNS
    )


def redact_text(text: str) -> str:
    if not isinstance(text, str):
        return ""

    for pattern, replacement in REDACTION_PATTERNS:
        text = re.sub(pattern, replacement, text)

    return text


def sanitize_records(records: list[dict]) -> list[dict]:
    """Drop authentication messages and redact common sensitive data."""
    sanitized = []

    for record in records:
        if is_auth_message(record):
            continue

        clean_record = record.copy()

        for field in ("text", "subject", "sender"):
            value = clean_record.get(field)
            if isinstance(value, str):
                clean_record[field] = redact_text(value)

        sanitized.append(clean_record)

    return sanitized