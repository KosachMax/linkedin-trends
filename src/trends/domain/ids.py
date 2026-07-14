import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMETERS = {
    "at_campaign",
    "at_medium",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "traffic_source",
    "yclid",
}


def canonicalize_url(value: str, ignored_query_params: list[str] | None = None) -> str:
    parsed = urlsplit(value.strip())
    ignored = TRACKING_PARAMETERS | {
        item.casefold() for item in ignored_query_params or []
    }
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in ignored
    ]
    query.sort(key=lambda pair: (pair[0].casefold(), pair[1]))
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(query), ""))


def stable_article_id(source_id: str, url: str) -> str:
    value = f"{source_id}:{canonicalize_url(url)}".encode()
    return hashlib.sha256(value).hexdigest()[:20]


def slugify(value: str) -> str:
    value = re.sub(r"[^a-z0-9а-яё]+", "-", value.lower(), flags=re.IGNORECASE)
    return value.strip("-")[:80] or "event"
