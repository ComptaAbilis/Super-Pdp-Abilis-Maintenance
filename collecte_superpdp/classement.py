"""Calcul du chemin de classement d'une facture reçue.

<SIREN> - <Société> / <SIRET> / <AAAA-MM> / <Fournisseur> (<SIREN fournisseur>) / <date>_<n° facture>.<ext>
"""

from __future__ import annotations

import re

SIRET_INCONNU = "SIRET non renseigné"
MOIS_INCONNU = "Date inconnue"
FOURNISSEUR_INCONNU = "Fournisseur inconnu"

# Caractères interdits par SharePoint / OneDrive dans un nom de fichier ou de dossier.
_INTERDITS = re.compile(r'[\\/:*?"<>|#%\x00-\x1f]')


def nettoyer(nom: str, max_len: int = 80) -> str:
    nom = _INTERDITS.sub("-", nom or "")
    nom = re.sub(r"\s+", " ", nom).strip()
    nom = nom[:max_len].strip(" .")
    return nom or "_"


def _valeur(obj) -> str:
    if isinstance(obj, dict):
        return str(obj.get("value") or "").strip()
    return str(obj or "").strip()


def _schema(obj) -> str:
    if isinstance(obj, dict):
        return str(obj.get("scheme") or "").strip()
    return ""


def _chiffres(texte: str) -> str:
    return re.sub(r"\D", "", texte or "")


def siret_acheteur(buyer: dict) -> str | None:
    """SIRET de l'établissement destinataire.

    Ordre de recherche :
    1. adresse électronique de facturation au format SIREN_SIRET[...] (cf. annuaire PPF) ;
    2. identifiant légal (BT-47) au schéma 0009 (SIRET) ;
    3. identifiants acheteur (BT-46) au schéma 0009.
    """
    buyer = buyer or {}
    adresse = _valeur(buyer.get("electronic_address"))
    parts = adresse.split("_")
    if len(parts) >= 2 and re.fullmatch(r"\d{14}", parts[1]):
        return parts[1]
    candidats = [buyer.get("legal_registration_identifier")] + list(buyer.get("identifiers") or [])
    for ident in candidats:
        valeur = _chiffres(_valeur(ident))
        if _schema(ident) == "0009" and len(valeur) == 14:
            return valeur
    for ident in candidats:
        valeur = _chiffres(_valeur(ident))
        if len(valeur) == 14:
            return valeur
    return None


def siren_partie(partie: dict) -> str | None:
    """SIREN d'un vendeur ou d'un acheteur (identifiant légal, sinon adresse électronique)."""
    partie = partie or {}
    for source in (partie.get("legal_registration_identifier"), partie.get("electronic_address")):
        valeur = _chiffres(_valeur(source).split("_")[0])
        if len(valeur) in (9, 14):
            return valeur[:9]
    return None


def chemin_facture(invoice: dict, societe: dict, extension: str) -> list[str]:
    """Liste des segments du chemin (dossiers puis nom de fichier) pour une facture reçue."""
    en = invoice.get("en_invoice") or {}
    seller = en.get("seller") or {}
    buyer = en.get("buyer") or {}

    siren = _chiffres(str(societe.get("number") or "")) or siren_partie(buyer) or "SIREN inconnu"
    nom_societe = societe.get("formal_name") or societe.get("trade_name") or ""
    dossier_societe = nettoyer(f"{siren} - {nom_societe}" if nom_societe else siren)

    siret = siret_acheteur(buyer) or SIRET_INCONNU

    date = str(en.get("issue_date") or "")
    mois = date[:7] if re.fullmatch(r"\d{4}-\d{2}", date[:7]) else MOIS_INCONNU

    nom_fournisseur = seller.get("name") or seller.get("trading_name") or FOURNISSEUR_INCONNU
    siren_fournisseur = siren_partie(seller)
    dossier_fournisseur = nettoyer(
        f"{nom_fournisseur} ({siren_fournisseur})" if siren_fournisseur else nom_fournisseur
    )

    numero = en.get("number") or f"id{invoice.get('id')}"
    prefixe = date if mois != MOIS_INCONNU else "sans-date"
    fichier = nettoyer(f"{prefixe}_{numero}", max_len=120) + extension

    return [dossier_societe, siret, mois, dossier_fournisseur, fichier]
