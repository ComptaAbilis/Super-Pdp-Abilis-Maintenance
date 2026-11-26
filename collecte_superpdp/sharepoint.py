"""Écriture dans une bibliothèque SharePoint via Microsoft Graph (application Entra, client_credentials).

Permissions recommandées : Sites.Selected, avec un accès « write » accordé uniquement au site cible.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote, urlparse

import requests

from .http import request

GRAPH = "https://graph.microsoft.com/v1.0"
SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024
CHUNK = 5 * 1024 * 1024  # multiple de 320 Kio


class SharePointDestination:
    """Destination SharePoint : site + bibliothèque + dossier racine."""

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        site_url: str,
        folder_path: str,
        library: str | None = None,
        session: requests.Session | None = None,
    ):
        self.session = session or requests.Session()
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self.root = folder_path.strip("/")
        self.drive_id = self._resolve_drive(site_url, library)
        self._known_folders: set[str] = set()

    # --- Authentification -------------------------------------------------
    def _headers(self) -> dict:
        if not self._token:
            resp = request(
                self.session,
                "POST",
                f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
            self._token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}"}

    def _call(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        return request(self.session, method, url, headers=headers, **kwargs)

    def _resolve_drive(self, site_url: str, library: str | None) -> str:
        u = urlparse(site_url)
        site = self._call("GET", f"{GRAPH}/sites/{u.hostname}:{u.path.rstrip('/')}").json()
        if not library:
            return self._call("GET", f"{GRAPH}/sites/{site['id']}/drive").json()["id"]
        drives = self._call("GET", f"{GRAPH}/sites/{site['id']}/drives").json()["value"]
        for drive in drives:
            if drive["name"] == library:
                return drive["id"]
        raise ValueError(f"Bibliothèque « {library} » introuvable sur {site_url}")

    # --- Chemins ----------------------------------------------------------
    def _full(self, segments: list[str]) -> str:
        return "/".join([self.root, *segments]) if self.root else "/".join(segments)

    def _item_url(self, path: str) -> str:
        return f"{GRAPH}/drives/{self.drive_id}/root:/{quote(path)}:"

    def _ensure_folder(self, segments: list[str]) -> None:
        """Crée les dossiers manquants (avec cache pour limiter les appels)."""
        parts = [p for p in self.root.split("/") if p] + segments
        for i in range(1, len(parts) + 1):
            path = "/".join(parts[:i])
            if path in self._known_folders:
                continue
            parent = "/".join(parts[: i - 1])
            parent_url = (
                f"{GRAPH}/drives/{self.drive_id}/root/children"
                if not parent
                else f"{self._item_url(parent)}/children"
            )
            try:
                self._call(
                    "POST",
                    parent_url,
                    json={"name": parts[i - 1], "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
                )
            except requests.HTTPError as err:
                if err.response is None or err.response.status_code != 409:  # 409 = existe déjà
                    raise
            self._known_folders.add(path)

    # --- Fichiers ---------------------------------------------------------
    def write(self, segments: list[str], content: bytes) -> str:
        """Écrit (ou remplace) un fichier ; segments = dossiers + nom de fichier."""
        self._ensure_folder(segments[:-1])
        path = self._full(segments)
        if len(content) <= SIMPLE_UPLOAD_MAX:
            self._call("PUT", f"{self._item_url(path)}/content", data=content)
            return path
        session = self._call(
            "POST",
            f"{self._item_url(path)}/createUploadSession",
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        ).json()
        total = len(content)
        for start in range(0, total, CHUNK):
            chunk = content[start : start + CHUNK]
            end = start + len(chunk) - 1
            # L'URL de session est pré-authentifiée : pas d'en-tête Authorization.
            request(
                self.session,
                "PUT",
                session["uploadUrl"],
                data=chunk,
                headers={"Content-Range": f"bytes {start}-{end}/{total}"},
            )
        return path

    def read_json(self, name: str) -> dict:
        try:
            return self._call("GET", f"{self._item_url(self._full([name]))}/content").json()
        except requests.HTTPError as err:
            if err.response is not None and err.response.status_code == 404:
                return {}
            raise

    def write_json(self, name: str, data: dict) -> None:
        self.write([name], json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))


class LocalDestination:
    """Destination locale, pour les essais (--dossier-local)."""

    def __init__(self, root: str):
        self.root = Path(root)

    def write(self, segments: list[str], content: bytes) -> str:
        path = self.root.joinpath(*segments)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    def read_json(self, name: str) -> dict:
        path = self.root / name
        return json.loads(path.read_text("utf-8")) if path.exists() else {}

    def write_json(self, name: str, data: dict) -> None:
        self.write([name], json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8"))
