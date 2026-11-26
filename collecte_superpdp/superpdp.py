"""Client minimal de l'API SUPER PDP (https://www.superpdp.tech/documentation).

- Authentification OAuth 2.1 client_credentials, une application (client_id/secret) par entreprise.
- Synchronisation des factures reçues avec GET /v1.beta/invoices?direction=in&starting_after_id=N,
  les id étant strictement croissants (cf. article « Synchronisation »).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterator

import requests

from .http import request

API_ROOT = "https://api.superpdp.tech"
TOKEN_URL = f"{API_ROOT}/oauth2/token"
BASE = f"{API_ROOT}/v1.beta"

EXTENSIONS = {
    "application/pdf": ".pdf",
    "application/xml": ".xml",
    "text/xml": ".xml",
    "application/json": ".json",
}


@dataclass
class InvoiceFile:
    content: bytes
    content_type: str

    @property
    def extension(self) -> str:
        return EXTENSIONS.get(self.content_type.split(";")[0].strip().lower(), ".bin")


class SuperPDPClient:
    def __init__(self, client_id: str, client_secret: str, session: requests.Session | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.session = session or requests.Session()
        self._token: str | None = None
        self._token_expiry = 0.0

    # --- Authentification -------------------------------------------------
    def _auth_headers(self) -> dict:
        if not self._token or time.time() > self._token_expiry - 60:
            resp = request(
                self.session,
                "POST",
                TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
            )
            payload = resp.json()
            self._token = payload["access_token"]
            self._token_expiry = time.time() + int(payload.get("expires_in", 3600))
        return {"Authorization": f"Bearer {self._token}"}

    def _get(self, path: str, **kwargs) -> requests.Response:
        return request(self.session, "GET", f"{BASE}{path}", headers=self._auth_headers(), **kwargs)

    # --- Entreprise -------------------------------------------------------
    def company(self) -> dict:
        """Entreprise liée au jeton : id, number (SIREN), formal_name, env (sandbox/production)."""
        return self._get("/companies/me").json()

    # --- Factures ---------------------------------------------------------
    def incoming_invoices(self, starting_after_id: int | None = None, limit: int = 50) -> Iterator[dict]:
        """Toutes les factures reçues dont l'id est > starting_after_id, par id croissant."""
        after = starting_after_id
        while True:
            params = [
                ("direction", "in"),
                ("order", "asc"),
                ("limit", str(limit)),
                ("expand[]", "en_invoice.seller"),
                ("expand[]", "en_invoice.buyer"),
            ]
            if after is not None:
                params.append(("starting_after_id", str(after)))
            page = self._get("/invoices", params=params).json()
            data = page.get("data") or []
            for invoice in data:
                yield invoice
            if not data or not page.get("has_after"):
                return
            after = data[-1]["id"]

    def invoice_file(self, invoice_id: int, fmt: str) -> InvoiceFile:
        """fmt : original, factur-x, ubl, cii ou en16931."""
        resp = self._get(f"/invoices/{invoice_id}", params={"format": fmt})
        return InvoiceFile(resp.content, resp.headers.get("Content-Type", ""))
