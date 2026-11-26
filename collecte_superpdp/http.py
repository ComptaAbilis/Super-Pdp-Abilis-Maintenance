"""Session HTTP commune avec reprises automatiques (429 / 5xx)."""

import time

import requests

RETRY_STATUS = {429, 500, 502, 503, 504}


def request(session: requests.Session, method: str, url: str, *, retries: int = 4, **kwargs) -> requests.Response:
    """Envoie une requête et réessaie sur les erreurs temporaires. Lève une exception sur les autres erreurs."""
    kwargs.setdefault("timeout", 60)
    for attempt in range(retries + 1):
        try:
            resp = session.request(method, url, **kwargs)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == retries:
                raise
            time.sleep(2**attempt)
            continue
        if resp.status_code in RETRY_STATUS and attempt < retries:
            delay = int(resp.headers.get("Retry-After", 2**attempt))
            time.sleep(min(delay, 60))
            continue
        if not resp.ok:
            raise requests.HTTPError(
                f"{method} {url} -> {resp.status_code}: {resp.text[:500]}", response=resp
            )
        return resp
    raise RuntimeError("unreachable")
