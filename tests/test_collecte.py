import json

from collecte_superpdp import main as m
from collecte_superpdp.classement import chemin_facture, nettoyer, siret_acheteur
from collecte_superpdp.sharepoint import LocalDestination
from collecte_superpdp.superpdp import InvoiceFile

SOCIETE = {"id": 7, "number": "853322915", "formal_name": "ABILIS HOLDING"}


def facture(id_, numero="F-2026/001", date="2026-11-03", adresse="853322915_85332291500010"):
    return {
        "id": id_,
        "direction": "in",
        "en_invoice": {
            "number": numero,
            "issue_date": date,
            "seller": {
                "name": "Fournisseur: Dupont & Fils",
                "legal_registration_identifier": {"scheme": "0002", "value": "123456789"},
            },
            "buyer": {"name": "Abilis", "electronic_address": {"scheme": "0225", "value": adresse}},
        },
    }


def test_chemin_complet():
    assert chemin_facture(facture(1), SOCIETE, ".pdf") == [
        "853322915 - ABILIS HOLDING",
        "85332291500010",
        "2026-11",
        "Fournisseur- Dupont & Fils (123456789)",
        "2026-11-03_F-2026-001.pdf",
    ]


def test_siret_absent_et_date_absente():
    f = facture(2, date="", adresse="853322915")
    seg = chemin_facture(f, SOCIETE, ".xml")
    assert seg[1] == "SIRET non renseigné"
    assert seg[2] == "Date inconnue"
    assert seg[4] == "sans-date_F-2026-001.xml"


def test_siret_par_identifiant_0009():
    assert siret_acheteur({"identifiers": [{"scheme": "0009", "value": "853 322 915 00028"}]}) == "85332291500028"


def test_nettoyer():
    assert nettoyer('a/b\\c:d*e?"f<g>h|i#j%k  ') == "a-b-c-d-e--f-g-h-i-j-k"
    assert nettoyer("...") == "_"


class FauxClient:
    pages = {}

    def __init__(self, client_id, client_secret):
        self.client_id = client_id

    def company(self):
        return SOCIETE

    def incoming_invoices(self, starting_after_id=None):
        return [f for f in self.pages[self.client_id] if starting_after_id is None or f["id"] > starting_after_id]

    def invoice_file(self, invoice_id, fmt):
        if fmt == "original":
            return InvoiceFile(b"<Invoice/>", "application/xml")
        return InvoiceFile(b"%PDF", "application/pdf")


def test_collecte_incrementale(tmp_path, monkeypatch):
    monkeypatch.setattr(m, "SuperPDPClient", FauxClient)
    monkeypatch.setenv("SUPERPDP_APPLICATIONS", json.dumps([{"client_id": "a", "client_secret": "s"}]))
    FauxClient.pages = {"a": [facture(10), facture(11, numero="F2")]}

    assert m.main(["--dossier-local", str(tmp_path)]) == 0
    mois = tmp_path / "853322915 - ABILIS HOLDING" / "85332291500010" / "2026-11"
    fichiers = sorted(p.name for p in mois.rglob("*.*"))
    assert fichiers == ["2026-11-03_F-2026-001.pdf", "2026-11-03_F-2026-001.xml", "2026-11-03_F2.pdf", "2026-11-03_F2.xml"]
    assert LocalDestination(str(tmp_path)).read_json(m.ETAT)["7"]["dernier_id"] == 11

    # Deuxième passage : seule la nouvelle facture est traitée.
    FauxClient.pages["a"].append(facture(12, numero="F3"))
    appels = []
    original = FauxClient.invoice_file
    monkeypatch.setattr(FauxClient, "invoice_file", lambda self, i, f: appels.append(i) or original(self, i, f))
    assert m.main(["--dossier-local", str(tmp_path)]) == 0
    assert set(appels) == {12}
    assert LocalDestination(str(tmp_path)).read_json(m.ETAT)["7"]["dernier_id"] == 12


class FausseReponse:
    def __init__(self, status=200, data=None):
        self.status_code, self._data, self.headers, self.text = status, data or {}, {}, ""
        self.ok = status < 400

    def json(self):
        return self._data


class FausseSessionGraph:
    """Simule Graph : dossiers créés par POST children, 409 si déjà existant."""

    def __init__(self):
        self.appels, self.existants, self.n = [], {"F0:2026-11": "EXIST"}, 0

    def request(self, method, url, **kw):
        self.appels.append((method, url))
        if "login.microsoftonline.com" in url:
            return FausseReponse(data={"access_token": "t", "expires_in": 3599})
        if method == "POST" and url.endswith("/children"):
            parent = url.split("/items/")[1].split("/")[0]
            if f"{parent}:{kw['json']['name']}" in self.existants:
                return FausseReponse(409)
            self.n += 1
            return FausseReponse(data={"id": f"F{self.n}"})
        if method == "GET" and ":/" in url:
            return FausseReponse(data={"id": "EXIST"})
        return FausseReponse(data={})


def test_sharepoint_adresse_par_drive_et_folder():
    from collecte_superpdp.sharepoint import SharePointDestination

    s = FausseSessionGraph()
    dest = SharePointDestination("ten", "cid", "sec", "DRV", "F0", session=s)
    dest.write(["2026-11", "Fourn A", "f 1.pdf"], b"x")
    dest.write(["2026-11", "Fourn A", "f2.pdf"], b"x")  # dossiers en cache : pas de nouvel appel
    urls = [u for m, u in s.appels if "graph" in u]
    assert all(u.startswith("https://graph.microsoft.com/v1.0/drives/DRV/items/") for u in urls)
    assert not any("/root" in u for u in urls)
    assert urls == [
        "https://graph.microsoft.com/v1.0/drives/DRV/items/F0/children",  # 2026-11 existe -> 409
        "https://graph.microsoft.com/v1.0/drives/DRV/items/F0:/2026-11",
        "https://graph.microsoft.com/v1.0/drives/DRV/items/EXIST/children",
        "https://graph.microsoft.com/v1.0/drives/DRV/items/F1:/f%201.pdf:/content",
        "https://graph.microsoft.com/v1.0/drives/DRV/items/F1:/f2.pdf:/content",
    ]
    assert sum("login" in u for _, u in s.appels) == 1  # jeton réutilisé


def test_jeton_superpdp_repli_basic_et_diagnostic():
    import pytest
    import requests as rq

    from collecte_superpdp.superpdp import SuperPDPClient

    class Session:
        def __init__(self, accepte_basic):
            self.accepte_basic, self.appels = accepte_basic, []

        def request(self, method, url, **kw):
            self.appels.append(kw)
            if "auth" in kw and self.accepte_basic:
                return FausseReponse(data={"access_token": "t", "expires_in": 3600})
            return FausseReponse(401)

    s = Session(accepte_basic=True)
    c = SuperPDPClient(" id1 \n", "sec\n", session=s)
    assert c._auth_headers() == {"Authorization": "Bearer t"}
    assert s.appels[0]["data"]["client_id"] == "id1" and s.appels[1]["auth"] == ("id1", "sec")

    with pytest.raises(rq.HTTPError) as e:
        SuperPDPClient("XXX", "a b", session=Session(False))._auth_headers()
    msg = str(e.value)
    assert "MODÈLE NON REMPLI" in msg and "contient des espaces" in msg and "a b" not in msg
