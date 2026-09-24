import re

INDIAN_MOBILE_PATTERN = re.compile(r"^[6-9]\d{9}$")


def normalize_indian_mobile(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    digits = re.sub(r"\D", "", value)
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if not INDIAN_MOBILE_PATTERN.fullmatch(digits):
        raise ValueError("Mobile number must be a valid 10-digit Indian mobile number")
    return f"+91{digits}"
