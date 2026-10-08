import re

USER_FIELDS = ["name", "email", "status", "role", "phone"]
REQUIRED_FIELDS = ["name", "email"]
STATUSES = ["active", "inactive"]
PHONE_MAX_LENGTH = 15  # matches users.phone VARCHAR(15)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_user(data):
    """Trim the name and email in place, e.g. ' ada@example.com ' becomes 'ada@example.com'.

    Runs before validate_user, so a whitespace-only value is rejected as empty.
    """
    if isinstance(data, dict):
        for field in ["name", "email"]:
            if isinstance(data.get(field), str):
                data[field] = data[field].strip()
    return data


def validate_user(data, partial=False):
    """Return an error message for an invalid user payload, or None if it's valid.

    partial=True is for PATCH, where every field is optional.
    """
    if not isinstance(data, dict) or not data:
        return "Request body must contain JSON"

    for field in data:
        if field not in USER_FIELDS:
            return f"Invalid field: {field}"

    if not partial:
        for field in REQUIRED_FIELDS:
            if field not in data:
                return f"Missing required field: {field}"

    for field in ["name", "email"]:
        if field in data and (not isinstance(data[field], str) or not data[field].strip()):
            return f"{field} must be a non-empty string"

    if "email" in data and not EMAIL_PATTERN.match(data["email"]):
        return "email must be a valid email address"

    if "status" in data and data["status"] not in STATUSES:
        return f"status must be one of: {', '.join(STATUSES)}"

    for field in ["role", "phone"]:
        if data.get(field) is not None and not isinstance(data[field], str):
            return f"{field} must be a string or null"

    if data.get("phone") is not None and len(data["phone"]) > PHONE_MAX_LENGTH:
        return f"phone must be at most {PHONE_MAX_LENGTH} characters"

    return None
