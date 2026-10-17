# surf-recommendation (FindYourWave)

Recommandation de spots de surf en Bretagne selon le niveau du surfeur et les prévisions.

```
Google Sheet (référentiels)  ──sync_sheets.py──►  ┌──────────────────────────┐
                                                  │  Supabase (PostgreSQL)   │ ◄── VS Code (SQLTools) / DBeaver
Open-Meteo Marine + Weather  ──collect.py─────►   │  5 tables                │ ◄── Streamlit (plus tard)
                                                  └──────────────────────────┘
GitHub Actions lance collect.py 3 fois par jour.
```

| Fichier | Rôle |
|---|---|
| `sql/001_schema.sql` | Crée les 5 tables du doc : `surf_spot_properties`, `surf_spot_conditions_reference`, `surf_level_conditions_reference`, `marine_forecast`, `spot_hour_scores` |
| `sync_sheets.py` | Lit les 3 onglets « Ref - … » du Sheet, vérifie les valeurs et les charge dans Supabase |
| `collect.py` | Appelle Open-Meteo pour chaque spot, calcule la marée et remplit `marine_forecast` (version « production » de `test_open_meteo.py`) |
| `tide.py` | Calcul de `tide_level_pct`, `tide_direction`, `tide_stage` (section « Calcul de tide_stage » du doc v3) |
| `config.py`, `db.py` | Paramètres (`.env`) et connexion Supabase |
| `test_open_meteo.py` | Ton script d'exploration, gardé tel quel |
| `workflows_a_deplacer/` | Automatisation GitHub Actions, à mettre dans `.github/workflows/` |
| `tests/` | Tests hors ligne (`python -m pytest tests`) |

---

## Pas à pas (Windows + VS Code)

Toutes les commandes se tapent dans le terminal de VS Code (**Terminal → Nouveau terminal**), **depuis le dossier `surf-recommendation`**. Si VS Code a ouvert le dossier parent `FindYourWave`, tape d'abord :

```powershell
cd surf-recommendation
```

La ligne du terminal doit finir par `...\FindYourWave\surf-recommendation>`.

### 1. Recréer l'environnement Python

Ton `.venv` a été créé dans l'ancien dossier `Projets Data\surf-recommendation`, avant d'être déplacé dans `FindYourWave`. Un venv déplacé casse `pip` et l'activation. Le plus simple est de le recréer :

```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

- Si PowerShell refuse l'activation (« l'exécution de scripts est désactivée sur ce système »), lance une fois `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, réponds `O`, puis relance la ligne d'activation.
- `(.venv)` doit apparaître au début de la ligne du terminal.
- Dans VS Code : `Ctrl+Shift+P` → **Python: Select Interpreter** → choisis celui qui contient `.venv`.

Vérification : `python -m pytest tests` affiche `4 passed`.

### 2. Créer les tables dans Supabase

1. Dans ton projet Supabase : menu de gauche **SQL Editor** → **New query**.
2. Colle tout le contenu de `sql/001_schema.sql` → **Run**. Tu dois voir « Success. No rows returned ».
3. Si tu as déjà lancé une ancienne version de `001_schema.sql` (sans les droits à la fin), lance aussi `sql/002_grants.sql` de la même façon. Sinon, les scripts Python reçoivent « permission denied for table » : depuis mai 2026, Supabase n'ouvre plus automatiquement les nouvelles tables à son API.
4. Menu **Table Editor** : les 5 tables apparaissent, et `surf_level_conditions_reference` contient déjà les 5 niveaux.

> L'intégration GitHub proposée par Supabase (Project Settings → Integrations) n'est pas utile pour le MVP : elle sert aux *branches* Supabase (une base de test par branche Git, payante) et aux migrations gérées par la CLI Supabase. Ici, c'est GitHub Actions qui parle à Supabase, avec les secrets de l'étape 7.

> Si tu avais déjà créé des tables avec les mêmes noms, le script ne les modifie pas (`create table if not exists`). Dans ce cas, supprime-les d'abord (Table Editor → clic droit → Delete table), ou dis-le-moi et je ferai un script de migration.

### 3. Remplir le fichier `.env`

1. Dans VS Code, duplique `.env.example` et renomme la copie en `.env` (exactement, avec le point).
2. Dans Supabase, **Project Settings** (roue crantée en bas du menu de gauche) :
   - **Data API** : copie la *Project URL* (`https://xxxx.supabase.co`) dans `SUPABASE_URL` ;
   - **API Keys** : sous le bloc *Publishable key*, descends jusqu'au bloc **Secret keys**. La clé `default` y est masquée (`sb_secret_••••`) : clique sur l'œil pour l'afficher, puis sur l'icône copier, et colle-la dans `SUPABASE_SECRET_KEY`. Si le bloc *Secret keys* est vide, clique sur **+ New secret key**, nomme-la `scripts`, puis copie-la.
   - Plan B : onglet **Legacy API Keys** en haut de la même page → ligne `service_role` → **Reveal** → copier. Elle marche exactement pareil dans `SUPABASE_SECRET_KEY`.
3. Enregistre (`Ctrl+S`). Le `.env` est exclu de Git par `.gitignore` : la clé secrète ne partira jamais sur GitHub.

> ⚠️ La clé secrète donne tous les droits sur la base : jamais dans le code, jamais dans Streamlit. L'app Streamlit utilisera plus tard la clé *publishable*, en lecture seule.

### 4. Corriger puis brancher le Google Sheet

1. **Correction obligatoire** dans l'onglet `Ref - surf_level_conditions_ref` : 6 hauteurs de houle sont devenues des dates (1,2 lu comme le 1er février). Sélectionne les colonnes B à K → **Format → Nombre → Nombre**, puis retape : débutant `swell_height_max` 1.2 ; intermédiaire `swell_height_ideal_max` 1.2 et `swell_height_max` 1.8 ; avancé `swell_height_ideal_max` 1.5 et `swell_height_max` 2.5 ; pro `swell_height_ideal_max` 2.5. Pour éviter que ça recommence : **Fichier → Paramètres → Paramètres régionaux : États-Unis**.
2. **Partager** → Accès général : « Tous les utilisateurs disposant du lien » → **Lecteur**.
3. Clique sur chacun des 3 onglets `Ref - …` et copie le nombre après `#gid=` dans l'URL vers `.env` : `GID_SPOT_PROPERTIES`, `GID_SPOT_CONDITIONS`, `GID_LEVEL_CONDITIONS`.
4. Lance :
   ```powershell
   python sync_sheets.py --dry-run
   python sync_sheets.py
   ```
   Le premier vérifie sans rien écrire, et il marche même sans clé Supabase : lance-le dès que les gid sont dans `.env`. Il lit directement le Sheet en ligne (pas un téléchargement .xlsx) et te dit s'il reste des cellules en date. Le second charge 14 spots, 14 conditions et 5 niveaux. S'il reste une erreur, le script liste les cellules à corriger et ne charge rien.

Tu préfères ne pas partager le Sheet ? **Fichier → Télécharger → .xlsx**, puis `python sync_sheets.py --xlsx "C:\chemin\vers\le_fichier.xlsx"`.

À relancer après chaque modification du Sheet.

### 5. Récupérer la météo et l'océan (Open-Meteo)

Aucune clé n'est nécessaire.

```powershell
python collect.py --spot la_torche --dry-run
python collect.py
```

- Le premier teste un seul spot sans écrire en base. Il crée `forecast_preview.csv`, que tu peux ouvrir pour vérifier.
- Le second remplit `marine_forecast` pour les 14 spots, soit 216 heures par spot (1 jour passé + 8 jours de prévision). Chaque ligne affichée donne le nombre d'heures, et combien sont sans marée. 3 à 6 heures sans marée, au début et à la fin, c'est normal.
- Tu peux relancer sans risque : les lignes existantes sont mises à jour, sans doublons.

Vérification dans Supabase, **SQL Editor** :
```sql
select spot_id, count(*), min(forecast_datetime), max(forecast_datetime)
from marine_forecast group by spot_id;
```

### 6. Voir la base depuis VS Code (optionnel)

1. Extensions (`Ctrl+Shift+X`) : installe **SQLTools** et **SQLTools PostgreSQL/Cockroach Driver**.
2. Dans Supabase, bouton **Connect** en haut de la page → onglet **Connection String** → méthode **Session pooler**. Note host, port (5432), database (`postgres`) et user (`postgres.xxxx`).
3. Dans VS Code, icône SQLTools (cylindre) → **Add New Connection** → **PostgreSQL**. Recopie ces valeurs, ajoute le mot de passe de la base (celui choisi à la création du projet, réinitialisable dans **Project Settings → Database**), puis **SSL : Enabled**. **Test Connection** → **Save**.

Prends bien le *Session pooler* : la connexion « Direct » ne marche pas sur la plupart des box (IPv6). Les mêmes paramètres marchent dans DBeaver.

### 7. Envoyer sur GitHub et automatiser

1. Dans l'explorateur Windows, crée dans `surf-recommendation` un dossier `.github`, puis dedans un dossier `workflows`, et déplaces-y les 2 fichiers de `workflows_a_deplacer`. Supprime ensuite `workflows_a_deplacer`.
2. Dans VS Code, onglet **Source Control** (`Ctrl+Shift+G`) : vérifie que `.env` n'apparaît **pas** dans la liste. Message « Ajout schéma Supabase et collecte Open-Meteo » → **Commit** → **Sync Changes**.
3. Sur github.com, dans ton repo, **Settings → Secrets and variables → Actions** :
   - onglet **Secrets** → **New repository secret** : `SUPABASE_URL` et `SUPABASE_SECRET_KEY` ;
   - onglet **Variables** : `GID_SPOT_PROPERTIES`, `GID_SPOT_CONDITIONS`, `GID_LEVEL_CONDITIONS`.
4. Onglet **Actions** → **collect** → **Run workflow** pour tester. Ensuite la collecte tourne seule à 4 h, 11 h et 17 h UTC. **sync-sheets** se lance à la main après une modif du Sheet.

---

## Dépannage

| Message | Cause probable |
|---|---|
| `SUPABASE_URL ou SUPABASE_SECRET_KEY manquant` | `.env` absent ou mal nommé (il doit s'appeler exactement `.env`, pas `.env.txt`) |
| `Fatal error in launcher` avec `pip` | venv déplacé : refaire l'étape 1 |
| `Invalid API key` | clé publishable collée à la place de la secrète |
| `Impossible de lire l'onglet … (HTTP 401/404)` | Sheet non partagé par lien, ou mauvais gid |
| `permission denied for table` (42501) | lancer `sql/002_grants.sql` dans le SQL Editor |
| `...python.exe n'est pas reconnu` | tu n'es pas dans le dossier `surf-recommendation` : `cd surf-recommendation` |
| `violates foreign key constraint` dans collect | lancer `sync_sheets.py` avant `collect.py` |
| `HTTP 429` Open-Meteo | trop d'appels rapprochés : attendre une minute |

## Prochaine étape

`spot_hour_scores` est créée mais encore vide. Elle sera remplie par `score.py` (éligibilité, sous-scores et score global du doc), à ajouter dans le workflow après `collect.py`.
