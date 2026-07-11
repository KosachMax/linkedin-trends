import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMETERS = {"fbclid", "gclid", "yclid"}


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMETERS
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(query), ""))


def stable_article_id(source_id: str, url: str) -> str:
    value = f"{source_id}:{canonicalize_url(url)}".encode()
    return hashlib.sha256(value).hexdigest()[:20]


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9а-яё]+", "-", value.lower(), flags=re.IGNORECASE)
    return value.strip("-")[:80] or "event"

