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
3. Il télécharge la facture (`GET /v1.beta/invoices/{id}?format=...`) et l'écrit dans le dossier SharePoint via Microsoft Graph.
4. Le point de reprise est stocké dans SharePoint, dans `_collecte_superpdp_etat.json` à la racine du dossier.

## Accès nécessaires (jamais dans le dépôt)

| Accès | Où le trouver | Variable |
|---|---|---|
| Une application SUPER PDP **par entreprise** | SUPER PDP > Applications > Nouvelle application… | secret `SUPERPDP_APPLICATIONS` (liste JSON) |
| Application Entra « WF Dossier SP Comptabilité » (`Files.SelectedOperations.Selected` sur un seul dossier) | Fiche technique de l'informatique | variables `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, secret `GRAPH_CLIENT_SECRET` |
| Dossier « Connexions Externes pour automatisations » | Fiche technique, section 3 | variables `SHAREPOINT_DRIVE_ID`, `SHAREPOINT_FOLDER_ID` |

Le dossier est toujours adressé par `driveId` + `folderId` : l'application n'a accès à rien d'autre.
Le secret Entra expire : le renouveler auprès de l'administrateur Microsoft 365 au moins 30 jours avant.

## Exécution planifiée (GitHub Actions)

Le workflow `.github/workflows/collecte.yml` tourne chaque jour à 5 h UTC et peut être lancé à la main (onglet *Actions* > *Run workflow*).
Dans *Settings > Secrets and variables > Actions* :

- **Secrets** : `SUPERPDP_APPLICATIONS`, `GRAPH_CLIENT_SECRET`
- **Variables** : `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `SHAREPOINT_DRIVE_ID`, `SHAREPOINT_FOLDER_ID`

## Essai en local

```bash
pip install -r requirements.txt
cp .env.example .env    # puis remplir les identifiants SUPER PDP (bac à sable pour commencer)
python -m collecte_superpdp --dossier-local sortie   # écrit dans ./sortie au lieu de SharePoint
python -m pytest
```
