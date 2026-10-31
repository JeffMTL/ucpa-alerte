# Alerte « place libérée » – UCPA Sport Station Nantes

Un petit script qui lit le planning **public** des cours et vous envoie une notification sur
votre téléphone (appli **ntfy**) dès qu'un cours complet que vous surveillez a de nouveau
au moins 1 place. Aucun compte UCPA, aucun mot de passe. Il ne réserve rien : vous cliquez
vous-même sur la notification pour ouvrir le planning.

## Installation (10 minutes, gratuit)

### 1. Recevoir les notifications
1. Installez l'appli **ntfy** (Android / iPhone).
2. « S'abonner à un sujet » avec un nom **long et aléatoire** que vous inventez, par exemple
   `ucpa-nantes-k7x9q2m4p1`. Ce nom sert de mot de passe : ne le partagez pas.

### 2. Mettre le script sur GitHub
1. Créez un compte sur github.com, puis un **dépôt public** (par ex. `ucpa-alerte`).
   Public = minutes d'exécution gratuites illimitées (à ma connaissance). Seuls la liste de
   cours et l'état y seront visibles, pas votre sujet ntfy.
2. Envoyez-y les fichiers de ce dossier (`Add file` > `Upload files`), **y compris**
   `.github/workflows/check.yml`. Si le dossier caché n'est pas pris, faites
   `Add file` > `Create new file`, tapez le nom `.github/workflows/check.yml` et collez le contenu.
3. `Settings` > `Secrets and variables` > `Actions` > `New repository secret` :
   nom `NTFY_TOPIC`, valeur = votre sujet ntfy (ex. `ucpa-nantes-k7x9q2m4p1`).
4. Si une étape d'enregistrement échoue : `Settings` > `Actions` > `General` >
   `Workflow permissions` > **Read and write permissions**.

### 3. Tester
Onglet **Actions** > « Surveillance UCPA » > **Run workflow** :
- `test` : vous devez recevoir « Test UCPA » sur le téléphone.
- `list` (avec `week` = 0, 1, 2…) : le journal affiche tous les cours de la semaine, et pour
  les cours complets, **la ligne toute prête à copier** dans `watch.json`.

## Utilisation au quotidien
Éditez `watch.json` (bouton crayon sur GitHub) : une ligne par cours à surveiller.

```json
[
  {"name": "Pilates",   "date": "02/11/2026", "start": "09h30"},
  {"name": "Body Pump", "date": "02/11/2026", "start": "12h15"}
]
```

- Le script vérifie toutes les ~5 minutes et ne vous alerte **qu'une fois** par libération.
- Si le cours se remplit puis se libère à nouveau, vous êtes prévenu de nouveau.
- Une fois le cours passé, la ligne est ignorée. Supprimez-la pour faire le ménage.
- Vous avez réservé ? Supprimez la ligne pour ne plus être alerté.

## À savoir
- **Non testé sur le vrai site** : je n'ai pu valider que la logique (données simulées au
  format réel). Le premier `list` est le vrai test. S'il échoue (site bloquant les
  serveurs GitHub, par exemple), copiez-moi le message d'erreur.
- **La fréquence de GitHub est « au mieux »** : 5 minutes au minimum, avec des retards
  possibles aux heures chargées. Pour plus de réactivité, lancez le script sur un PC ou un
  Raspberry Pi : `NTFY_TOPIC=... python3 ucpa_alert.py loop --every 120`.
- GitHub peut désactiver les tâches planifiées d'un dépôt inactif depuis 60 jours : réactivez-les
  dans l'onglet Actions si besoin.
- Si le planning devient illisible pendant ~30 min (site modifié, accès refusé), le script
  vous envoie une notification pour vous le dire.
- Respectez les conditions d'utilisation du site : le script fait une seule lecture par
  semaine surveillée, toutes les 5 minutes. N'abaissez pas cet intervalle.
- Outil personnel, non affilié à l'UCPA.
