"""Collecte des factures reçues sur SUPER PDP et classement dans SharePoint.

Usage :
    python -m collecte_superpdp                       # écrit dans SharePoint
    python -m collecte_superpdp --dossier-local out   # essai : écrit dans un dossier local

Configuration par variables d'environnement (ou fichier .env, jamais commité) : voir .env.example.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys

import requests

from .classement import chemin_facture
from .sharepoint import LocalDestination, SharePointDestination
from .superpdp import SuperPDPClient

ETAT = "_collecte_superpdp_etat.json"
log = logging.getLogger("collecte_superpdp")


def _env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(f"Variable d'environnement manquante : {name}")
    return value


def _applications() -> list[dict]:
    """SUPERPDP_APPLICATIONS = [{"client_id": "...", "client_secret": "..."}, ...] (une par entreprise)."""
    apps = json.loads(_env("SUPERPDP_APPLICATIONS"))
    if not isinstance(apps, list) or not all("client_id" in a and "client_secret" in a for a in apps):
        sys.exit("SUPERPDP_APPLICATIONS doit être une liste JSON d'objets {client_id, client_secret}")
    return apps


def _destination(dossier_local: str | None):
    if dossier_local:
        return LocalDestination(dossier_local)
    return SharePointDestination(
        tenant_id=_env("GRAPH_TENANT_ID"),
        client_id=_env("GRAPH_CLIENT_ID"),
        client_secret=_env("GRAPH_CLIENT_SECRET"),
        site_url=_env("SHAREPOINT_SITE_URL"),
        folder_path=os.environ.get("SHAREPOINT_FOLDER_PATH", ""),
        library=os.environ.get("SHAREPOINT_LIBRARY") or None,
    )


def enregistrer_facture(client: SuperPDPClient, dest, invoice: dict, societe: dict) -> list[str]:
    """Enregistre la version PDF (Factur-X) et, si différent, le fichier d'origine (XML)."""
    ecrits = []
    original = client.invoice_file(invoice["id"], "original")
    if original.extension != ".pdf":
        try:
            pdf = client.invoice_file(invoice["id"], "factur-x")
            ecrits.append(dest.write(chemin_facture(invoice, societe, ".pdf"), pdf.content))
        except requests.HTTPError as err:
            log.warning("Facture %s : conversion PDF impossible (%s), seul l'original est gardé", invoice["id"], err)
    ecrits.append(dest.write(chemin_facture(invoice, societe, original.extension), original.content))
    return ecrits


def collecter(app: dict, dest, etat: dict, sauvegarder) -> int:
    """Collecte les nouvelles factures d'une entreprise. Retourne le nombre de factures traitées."""
    client = SuperPDPClient(app["client_id"], app["client_secret"])
    societe = client.company()
    cle = str(societe["id"])
    dernier = etat.get(cle, {}).get("dernier_id")
    log.info("%s (%s) : reprise après la facture %s", societe.get("formal_name"), societe.get("number"), dernier)

    n = 0
    for invoice in client.incoming_invoices(starting_after_id=dernier):
        for chemin in enregistrer_facture(client, dest, invoice, societe):
            log.info("  + %s", chemin)
        # On n'avance le point de reprise qu'après un enregistrement réussi : aucune facture sautée.
        etat[cle] = {"dernier_id": invoice["id"], "siren": societe.get("number"), "nom": societe.get("formal_name")}
        n += 1
        if n % 20 == 0:
            sauvegarder()
    sauvegarder()
    return n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dossier-local", help="écrit dans ce dossier local au lieu de SharePoint (essai)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(message)s")

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    apps = _applications()
    dest = _destination(args.dossier_local)
    etat = dest.read_json(ETAT)

    def sauvegarder():
        dest.write_json(ETAT, etat)

    erreurs = 0
    for i, app in enumerate(apps, 1):
        try:
            n = collecter(app, dest, etat, sauvegarder)
            log.info("Application %d : %d nouvelle(s) facture(s)", i, n)
        except Exception:  # une entreprise en erreur ne bloque pas les autres
            erreurs += 1
            log.exception("Application %d : erreur, la collecte reprendra au prochain passage", i)
            sauvegarder()
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
