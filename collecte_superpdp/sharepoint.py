"""Écriture dans le dossier SharePoint autorisé, via Microsoft Graph (application Entra, client_credentials).

L'application a la permission Files.SelectedOperations.Selected sur UN dossier : on l'adresse toujours
par driveId + folderId (les chemins depuis la racine /root:/... et la recherche sur le site sont refusés).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote

import requests

from .http import request

GRAPH = "https://graph.microsoft.com/v1.0"
SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024
CHUNK = 5 * 1024 * 1024  # multiple de 320 Kio


class SharePointDestination:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        drive_id: str,
        folder_id: str,
        session: requests.Session | None = None,
    ):
        self.session = session or requests.Session()
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._token: str | None = None
        self._token_expiry = 0.0
        self.drive_id = drive_id
        self.folder_id = folder_id
        self._folder_ids: dict[tuple[str, ...], str] = {(): folder_id}

    # --- Authentification (jeton mis en cache jusqu'à expiration) ----------
    def _headers(self) -> dict:
        if not self._token or time.time() > self._token_expiry - 120:
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
            payload = resp.json()
            self._token = payload["access_token"]
            self._token_expiry = time.time() + int(payload.get("expires_in", 3599))
        return {"Authorization": f"Bearer {self._token}"}

    def _call(self, method: str, url: str, **kwargs) -> requests.Response:
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        return request(self.session, method, url, headers=headers, **kwargs)

    def _item(self, item_id: str) -> str:
        return f"{GRAPH}/drives/{self.drive_id}/items/{item_id}"

    # --- Dossiers ---------------------------------------------------------
    def _folder(self, segments: list[str]) -> str:
        """Id du sous-dossier (créé s'il n'existe pas), relatif au dossier autorisé."""
        key: tuple[str, ...] = ()
        parent = self.folder_id
        for name in segments:
            key = (*key, name)
            if key not in self._folder_ids:
                try:
                    item = self._call(
                        "POST",
                        f"{self._item(parent)}/children",
                        json={"name": name, "folder": {}, "@microsoft.graph.conflictBehavior": "fail"},
                    ).json()
                except requests.HTTPError as err:
                    if err.response is None or err.response.status_code != 409:  # 409 = existe déjà
                        raise
                    item = self._call("GET", f"{self._item(parent)}:/{quote(name)}").json()
                self._folder_ids[key] = item["id"]
            parent = self._folder_ids[key]
        return parent

    # --- Fichiers ---------------------------------------------------------
    def write(self, segments: list[str], content: bytes) -> str:
        """Écrit (ou remplace) un fichier ; segments = sous-dossiers + nom de fichier."""
        parent = self._folder(segments[:-1])
        target = f"{self._item(parent)}:/{quote(segments[-1])}:"
        if len(content) <= SIMPLE_UPLOAD_MAX:
            self._call(
                "PUT",
                f"{target}/content",
                params={"@microsoft.graph.conflictBehavior": "replace"},
                data=content,
                headers={"Content-Type": "application/octet-stream"},
            )
        else:
            upload = self._call(
                "POST",
                f"{target}/createUploadSession",
                json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            ).json()
            total = len(content)
            for start in range(0, total, CHUNK):
                chunk = content[start : start + CHUNK]
                # L'URL de session est pré-authentifiée : pas d'en-tête Authorization.
                request(
                    self.session,
                    "PUT",
                    upload["uploadUrl"],
                    data=chunk,
                    headers={"Content-Range": f"bytes {start}-{start + len(chunk) - 1}/{total}"},
                )
        return "/".join(segments)

    def read_json(self, name: str) -> dict:
        try:
            return self._call("GET", f"{self._item(self.folder_id)}:/{quote(name)}:/content").json()
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
