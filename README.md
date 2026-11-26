# Collecte des factures SUPER PDP vers SharePoint

Récupère chaque jour les factures **reçues** sur SUPER PDP et les range dans un dossier SharePoint :

```
<SIREN> - <Société>/
  <SIRET de l'établissement destinataire>/
    <AAAA-MM>/                       (mois de la date de facture)
      <Fournisseur> (<SIREN fournisseur>)/
        <AAAA-MM-JJ>_<n° facture>.pdf   (version lisible, Factur-X)
        <AAAA-MM-JJ>_<n° facture>.xml   (fichier d'origine UBL/CII, s'il n'est pas déjà un PDF)
```

Si le SIRET n'est pas renseigné dans la facture, elle va dans `SIRET non renseigné`.

## Fonctionnement

1. Pour chaque entreprise configurée, le script s'authentifie sur l'API SUPER PDP (OAuth `client_credentials`).
2. Il liste les factures reçues (`GET /v1.beta/invoices?direction=in`) dont l'id est supérieur au dernier traité.
   Les id SUPER PDP sont strictement croissants : aucune facture n'est oubliée ni téléchargée deux fois.
3. Il télécharge la facture (`GET /v1.beta/invoices/{id}?format=...`) et l'écrit dans SharePoint via Microsoft Graph.
4. Le point de reprise est stocké dans SharePoint, dans `_collecte_superpdp_etat.json` à la racine du dossier.

## Accès nécessaires (jamais dans le dépôt)

| Accès | Où le créer | Variable |
|---|---|---|
| Une application SUPER PDP **par entreprise** | SUPER PDP > Applications > Nouvelle application… | `SUPERPDP_APPLICATIONS` (liste JSON) |
| Une application Microsoft Entra, permission Graph **Sites.Selected** + accès `write` au site | Service informatique (voir `docs/demande-informatique.md`) | `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET` |
| Site et dossier SharePoint | — | `SHAREPOINT_SITE_URL`, `SHAREPOINT_LIBRARY` (vide = bibliothèque par défaut), `SHAREPOINT_FOLDER_PATH` |

## Exécution planifiée (GitHub Actions)

Le workflow `.github/workflows/collecte.yml` tourne chaque jour à 5 h UTC et peut être lancé à la main (onglet *Actions* > *Run workflow*).
Dans *Settings > Secrets and variables > Actions* :

- **Secrets** : `SUPERPDP_APPLICATIONS`, `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_CLIENT_SECRET`
- **Variables** : `SHAREPOINT_SITE_URL`, `SHAREPOINT_LIBRARY`, `SHAREPOINT_FOLDER_PATH`

## Essai en local

```bash
pip install -r requirements.txt
cp .env.example .env    # puis remplir les identifiants SUPER PDP (bac à sable pour commencer)
python -m collecte_superpdp --dossier-local sortie   # écrit dans ./sortie au lieu de SharePoint
python -m pytest
```
