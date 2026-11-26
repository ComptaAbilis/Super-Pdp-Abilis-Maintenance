# Demande au service informatique : accès SharePoint pour la collecte SUPER PDP

Bonjour,

Nous mettons en place un script qui dépose automatiquement les factures fournisseurs reçues sur notre Plateforme Agréée (SUPER PDP) dans SharePoint. Il a besoin d'une application Microsoft Entra limitée à un seul site.

1. **Créer une inscription d'application** dans Microsoft Entra ID (par ex. « Collecte factures SUPER PDP »), à locataire unique.
2. **Permission API** : Microsoft Graph > *Autorisations d'application* > `Sites.Selected`, puis *Accorder le consentement administrateur*.
3. **Donner l'accès en écriture au seul site** `https://groupeabilisfr.sharepoint.com/sites/msteams_fa2c43_543535-CommunityDAF` :
   ```
   POST https://graph.microsoft.com/v1.0/sites/{site-id}/permissions
   { "roles": ["write"],
     "grantedToIdentities": [{ "application": { "id": "<client_id>", "displayName": "Collecte factures SUPER PDP" } }] }
   ```
   (ou en PowerShell PnP : `Grant-PnPAzureADAppSitePermission -AppId <client_id> -DisplayName "Collecte factures SUPER PDP" -Site <url du site> -Permissions Write`)
4. **Créer un secret client** (durée 12 ou 24 mois) et nous transmettre de façon sécurisée : l'ID du locataire (tenant), l'ID de l'application (client_id) et le secret.

L'application n'aura accès à aucun autre site ni à aucune boîte mail.

Merci !
