# FindYourWave · surf-recommendation

Recommandation de spots de surf en Bretagne, heure par heure, selon le niveau du surfeur.

Ce dépôt contient le **pipeline de données** du projet : il charge le référentiel des spots, collecte les prévisions océan et météo trois fois par jour, calcule la marée et prépare la table des scores. Il applique les specs du document *FindYourWave : Algorithme de recommandation pour le surf* (v3).

```
Google Sheet (référentiels, saisis à la main)
        │  sync_sheets.py : nettoyage + contrôles, tout ou rien
        ▼
┌──────────────────────────────────────────────┐
│  Supabase (PostgreSQL), 5 tables             │
│  surf_spot_properties                        │
│  surf_spot_conditions_reference              │
│  surf_level_conditions_reference             │
│  marine_forecast      ◄── collect.py ◄── Open-Meteo Marine + Weather
│  spot_hour_scores     ◄── score.py (à venir) │
└──────────────────────────────────────────────┘
        ▲
GitHub Actions : sync + collecte à 4 h, 11 h et 17 h UTC
```

**État :** 14 spots, 5 niveaux, 216 heures de prévisions par spot (J-1 à J+8), rafraîchies 3 fois par jour. Les données sont vérifiées par les requêtes SQL du dossier `sql/` (voir [Qualité des données](#qualité-des-données)). Le calcul des scores (`score.py`) est la prochaine étape.

## Stack

| Brique | Rôle |
|---|---|
| Python 3.13 (pandas, requests, supabase-py) | Scripts d'ingestion et de calcul |
| Supabase (PostgreSQL) | Stockage, contraintes d'intégrité, API en lecture |
| Google Sheets | Saisie des référentiels par un humain (spots, conditions idéales, seuils par niveau) |
| Open-Meteo Marine + Weather | Prévisions horaires gratuites, sans clé |
| GitHub Actions | Planification (cron) et exécution, secrets chiffrés |

## Contenu du dépôt

| Fichier | Rôle |
|---|---|
| `sql/001_schema.sql` | Les 5 tables du doc, avec leurs contraintes, les droits et la sécurité (RLS) |
| `sql/002_grants.sql` | Droits d'accès de l'API Supabase (déjà inclus à la fin de 001) |
| `sql/003_checks.sql` | 20 contrôles d'alimentation : référentiels, fraîcheur, trous, valeurs vides, plausibilité |
| `sql/004_null_columns.sql` | Taux de remplissage de chaque colonne de chaque table |
| `sql/005_tide_check.sql` | Vérification du calcul de la marée contre la hauteur d'eau brute |
| `sync_sheets.py` | Google Sheet → 3 tables de référence |
| `collect.py` | Open-Meteo → `marine_forecast` |
| `tide.py` | Calcul de `tide_level_pct`, `tide_direction`, `tide_stage` |
| `config.py`, `db.py` | Paramètres (lus dans `.env` ou les secrets GitHub) et connexion Supabase |
| `tests/test_pipeline.py` | Tests unitaires hors ligne (marée, rejet des dates du Sheet, assemblage des lignes) |
| `.github/workflows/` | `collect.yml` (3×/jour) et `sync_sheets.yml` (manuel) |

## Modèle de données

Les tables reprennent la section « Modèle de données » du doc. Les choix d'implémentation sont indiqués à droite.

| Table | Grain | Source | Choix d'implémentation |
|---|---|---|---|
| `surf_spot_properties` | 1 ligne par spot | Sheet « Ref - surf_spot_properties » | `spot_id` en clé, en minuscules. Coordonnées et orientation bornées par des CHECK. |
| `surf_spot_conditions_reference` | 1 ligne par spot | Sheet « Ref - surf_spot_conditions_ref » | Clé étrangère vers le spot. `ideal_tide_stage` vaut `toutes` par défaut. Les fenêtres circulaires (ex. 330 → 30) sont acceptées. |
| `surf_level_conditions_reference` | 1 ligne par niveau | Sheet « Ref - surf_level_conditions_ref » | Les CHECK imposent `min ≤ idéal min ≤ idéal max ≤ max` : un seuil mal saisi est refusé par la base elle-même. |
| `marine_forecast` | 1 ligne par spot et par heure | Open-Meteo + `tide.py` | Unicité `(spot_id, forecast_datetime)` : chaque collecte met à jour les heures existantes, sans doublon. |
| `spot_hour_scores` | 1 ligne par spot, heure et niveau | `score.py` (à venir) | Les CHECK garantissent qu'un créneau non éligible a une raison et pas de score global. |

Les « enum » du doc sont des CHECK sur du texte plutôt que des types ENUM Postgres : ajouter une valeur revient à modifier une ligne.

**Sécurité.** Row Level Security est activé partout, avec une politique de lecture seule pour la clé publique (la future app Streamlit). Seuls les scripts écrivent, avec la clé secrète. Cette clé n'est jamais dans le code : elle vit dans `.env` en local (exclu de Git) et dans les *Secrets* GitHub pour l'automatisation.

## Ce que fait le code, par rapport aux specs

### 1. Référentiels : `sync_sheets.py`

Le doc prévoit une saisie humaine dans Google Sheets. Le script lit chaque onglet (export CSV en ligne, ou un `.xlsx` local avec `--xlsx`) puis applique les transformations de la colonne « Transfo » du doc :

| Transformation | Exemple |
|---|---|
| Identifiants en minuscules, espaces remplacés par `_` | `La Torche` → `la_torche` |
| Valeurs d'enum en minuscules et sans accents | `Intermédiaire` → `intermediaire`, `Mi-marée` → `mi-maree` |
| Décimales françaises acceptées | `1,2` → `1.2` |
| Nombres transformés en dates par Google Sheets rejetés | `01/02` à la place de `1,2` → erreur explicite |
| Valeurs contrôlées contre les listes du doc | `min_level` ∈ {debutant, intermediaire, avance, expert, pro} |
| Bornes vérifiées | orientations 0–360, crowd 1–5, houle 0–10 m |
| Seuils ordonnés par niveau | `swell_height_min ≤ … ≤ swell_height_max` |
| Cohérence entre onglets | chaque spot des conditions existe dans les propriétés |

Le chargement est **tout ou rien** : à la moindre erreur, rien n'est écrit et le script liste les cellules à corriger. L'en-tête est détecté automatiquement, même s'il y a des lignes vides au-dessus du tableau ou des unités dans le nom de colonne (`period_min (sec)`).

### 2. Prévisions : `collect.py`

Pour chaque spot de `surf_spot_properties` (lus en base, donc un spot ajouté au Sheet est collecté automatiquement) :

| Colonne `marine_forecast` | Champ Open-Meteo | API |
|---|---|---|
| `swell_height_m` | `swell_wave_height` | Marine |
| `swell_period_s` | `swell_wave_period` | Marine |
| `swell_direction_deg` | `swell_wave_direction` | Marine |
| `water_temp_c` | `sea_surface_temperature` | Marine |
| `sea_level_height_m` | `sea_level_height_msl` | Marine |
| `wind_speed_kmh` | `wind_speed_10m` (forcé en km/h) | Weather |
| `wind_direction_deg` | `wind_direction_10m` | Weather |
| `air_temp_c` | `temperature_2m` | Weather |
| `uv_index` | `uv_index` | Weather |
| `precipitation_mm` | `precipitation` | Weather |

- **Unités et conventions du doc :** heures en UTC (`timezone=GMT`), vent en km/h, directions en « d'où ça vient », comme les fenêtres du référentiel.
- **Fenêtre :** `past_days=1` et `forecast_days=8`. Le jour passé et le jour en plus servent à encadrer chaque heure utile par une basse mer et une pleine mer, nécessaires au calcul de la marée.
- **Sobriété :** une seule requête par API pour tous les spots (Open-Meteo accepte des listes de coordonnées), soit 2 appels par collecte. En cas d'échec : 3 essais avec attente croissante, puis un nouvel essai spot par spot.
- **Traçabilité :** `data_source` et `retrieved_at` sur chaque ligne. Le futur `forecast_retrieved_at` des scores pointe vers cette collecte.
- Le script sort en erreur si un spot échoue, ce qui empêchera le scoring de tourner sur des données incomplètes.

### 3. Marée : `tide.py`

Open-Meteo donne la hauteur d'eau, pas le stade de la marée. `tide.py` applique la section « Calcul de tide_stage » du doc v3 :

1. Repérer les basses et pleines mers (minima et maxima locaux de `sea_level_height_m`). Un palier de plusieurs heures à la même hauteur ne compte qu'une fois.
2. Entre deux extrêmes, calculer la progression de l'heure : `tide_level_pct` vaut 0 à la basse mer et 1 à la pleine mer, en montée comme en descente.
3. `tide_direction` vaut `montante` entre une basse et une pleine mer, `descendante` sinon. Une pleine mer est le début de la descente, une basse mer le début de la montée.
4. `tide_stage` : `basse` si pct < 0,3, `pleine` si pct > 0,7, `mi-maree` sinon.

Les quelques heures avant le premier extrême et après le dernier restent vides, car on ne peut pas les situer dans un cycle. Grâce à la marge J-1 et J+8, elles tombent hors de la fenêtre utile (J-1 à J+7).

### 4. Scores : `score.py` (prochaine étape)

`spot_hour_scores` est créée et contrainte, mais encore vide. `score.py` calculera pour chaque spot, heure et niveau :

- **l'éligibilité** : niveau du spot, houle trop forte, vent trop fort, données manquantes ;
- **les sous-scores** houle (hauteur et direction), période, vent (vitesse et direction) et marée ;
- **le score global** pondéré du doc.

Il s'appuiera sur les règles du doc v3 qui ne sont pas stockées : la traduction de `ideal_tide_stage` en plage de `tide_level_pct`, les fenêtres par défaut quand un spot n'en a pas (houle = orientation ± 30°, vent offshore = orientation + 180° ± 45°), la gestion des fenêtres qui passent par le nord, et l'affichage en heure de Paris.

Prévu en V2 : `tide_coefficient` (source SHOM), aujourd'hui vide, et `crowd_level`, stocké mais pas utilisé par l'algorithme.

## Qualité des données

Les trois requêtes de contrôle se lancent dans le SQL Editor de Supabase, en lecture seule. Résultats sur les données réelles :

| Requête | Ce qu'elle vérifie | Résultat |
|---|---|---|
| `003_checks.sql` | 14 spots tous renseignés et collectés, collecte de moins de 13 h, prévisions jusqu'à J+7, aucune heure manquante, aucune valeur vide sur la houle, le vent, les températures et la hauteur d'eau, valeurs plausibles, 3 stades de marée présents | 20 contrôles sur 20 OK |
| `004_null_columns.sql` | Taux de remplissage de chaque colonne | 100 % partout, sauf les 3 colonnes de marée (96 %, ce sont les heures de bord de fenêtre) et `tide_coefficient` (0 %, prévu en V2) |
| `005_tide_check.sql` | Le stade suit la règle du doc. L'eau monte bien quand la marée est montante et baisse quand elle est descendante. Les basses et pleines mers sont bien des creux et des pics. | 0 erreur. Environ 12,2 h entre deux basses mers, ce qui correspond au cycle semi-diurne réel (12 h 25). |

Les tests unitaires (`python -m pytest tests`) vérifient sans réseau la marée sur des courbes simulées, le rejet des dates parasites du Sheet et l'assemblage des lignes.

## Lancer le projet

Prérequis : Python 3.13, un projet Supabase et un Google Sheet partagé en lecture par lien.

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash) ; sous macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # puis renseigner l'URL et la clé secrète Supabase, et les gid des onglets
```

1. Dans Supabase, **SQL Editor** : exécuter `sql/001_schema.sql`.
2. Charger les référentiels : `python sync_sheets.py --dry-run` (vérifie seulement), puis `python sync_sheets.py`.
3. Collecter : `python collect.py --spot la_torche --dry-run` (un spot, aperçu dans `forecast_preview.csv`), puis `python collect.py`.
4. Contrôler : exécuter `sql/003_checks.sql`, `004_null_columns.sql` et `005_tide_check.sql`.

**Automatisation.** Dans GitHub, **Settings → Secrets and variables → Actions** :
- *Secrets* (chiffrés, invisibles même dans les logs) : `SUPABASE_URL`, `SUPABASE_SECRET_KEY` ;
- *Variables* : `GID_SPOT_PROPERTIES`, `GID_SPOT_CONDITIONS`, `GID_LEVEL_CONDITIONS`.

Le workflow `collect` synchronise alors le Sheet puis collecte les prévisions à 4 h, 11 h et 17 h UTC. Il peut aussi se lancer à la main depuis l'onglet **Actions**.
