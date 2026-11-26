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
