# FindYourWave · surf-recommendation

Recommandation de spots de surf en Bretagne, heure par heure, selon le niveau du surfeur.

Ce dépôt contient le **pipeline de données** et le **moteur de scoring** du projet : il charge le référentiel des spots, collecte les prévisions océan et météo trois fois par jour, calcule la marée, puis note chaque spot, heure par heure, pour chacun des 5 niveaux. Il applique les specs du document *FindYourWave : Algorithme de recommandation pour le surf* (v5).

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
│  spot_hour_scores     ◄── score.py           │
└──────────────────────────────────────────────┘
        ▲
GitHub Actions : sync, collecte puis scoring à 4 h, 11 h et 17 h UTC
```

**État :** 14 spots, 5 niveaux, 216 heures de prévisions par spot (J-1 à J+8) et 11 760 scores (14 spots × 168 h × 5 niveaux), rafraîchis 3 fois par jour. Les données sont vérifiées par les requêtes SQL du dossier `sql/` (voir [Qualité des données](#qualité-des-données)). L'interface Streamlit (`app.py`) lit ces scores en lecture seule et affiche, pour chaque jour choisi, les 5 meilleurs spots avec leur créneau, leur explication et une carte.

## Stack

| Brique | Rôle |
|---|---|
| Python 3.13 (pandas, requests, supabase-py) | Scripts d'ingestion et de calcul |
| Supabase (PostgreSQL) | Stockage, contraintes d'intégrité, API en lecture |
| Google Sheets | Saisie des référentiels par un humain (spots, conditions idéales, seuils par niveau) |
| Open-Meteo Marine + Weather | Prévisions horaires gratuites, sans clé |
| GitHub Actions | Planification (cron) et exécution, secrets chiffrés |
| Streamlit + pydeck | Interface web (ordinateur et téléphone) et carte des spots |

## Contenu du dépôt

| Fichier | Rôle |
|---|---|
| `sql/001_schema.sql` | Les 5 tables du doc, avec leurs contraintes, les droits et la sécurité (RLS) |
| `sql/002_grants.sql` | Droits d'accès de l'API Supabase (déjà inclus à la fin de 001) |
| `sql/003_checks.sql` | 20 contrôles d'alimentation : référentiels, fraîcheur, trous, valeurs vides, plausibilité |
| `sql/004_null_columns.sql` | Taux de remplissage de chaque colonne de chaque table |
| `sql/005_tide_check.sql` | Vérification du calcul de la marée contre la hauteur d'eau brute |
| `sql/006_scores_check.sql` | Contrôle des scores : volume, fraîcheur, éligibilité par niveau, répartition |
| `sql/007_daylight.sql` | Migration : colonne `is_daylight` et raison `nuit` (déjà incluses dans 001 pour une nouvelle base) |
| `sql/008_swell_too_low.sql` | Migration : raison `houle_trop_faible` du scoring v1 (déjà incluse dans 001 pour une nouvelle base) |
| `sync_sheets.py` | Google Sheet → 3 tables de référence |
| `collect.py` | Open-Meteo → `marine_forecast` |
| `tide.py` | Calcul de `tide_level_pct`, `tide_direction`, `tide_stage` |
| `score.py` | Éligibilité, sous-scores et score global → `spot_hour_scores` |
| `config.py`, `db.py` | Paramètres (lus dans `.env` ou les secrets GitHub) et connexion Supabase |
| `app.py` | Interface Streamlit : formulaire, résultats par jour, carte, rafraîchissement, export CSV |
| `selection.py` | Filtres distance, dates et horaires (heure de Paris), meilleur créneau par spot, top 5, raison d'absence |
| `explain.py` | Explications en français (templates, sans IA), détail du score, libellés |
| `ui.py` | Habillage : CSS, bandeau, cartes de résultat, échelle de couleurs « Lagon » |
| `.streamlit/` | Thème de l'app (`config.toml`) et modèle de secrets (`secrets.toml.example`) |
| `tests/` | Tests unitaires hors ligne : marée, rejet des dates du Sheet, assemblage des lignes, chaque règle de scoring, sélection, explications, habillage |
| `.github/workflows/` | `collect.yml` (3×/jour) et `sync_sheets.yml` (manuel) |

## Modèle de données

Les tables reprennent la section « Modèle de données » du doc. Les choix d'implémentation sont indiqués à droite.

| Table | Grain | Source | Choix d'implémentation |
|---|---|---|---|
| `surf_spot_properties` | 1 ligne par spot | Sheet « Ref - surf_spot_properties » | `spot_id` en clé, en minuscules. Coordonnées et orientation bornées par des CHECK. |
| `surf_spot_conditions_reference` | 1 ligne par spot | Sheet « Ref - surf_spot_conditions_ref » | Clé étrangère vers le spot. `ideal_tide_stage` vaut `toutes` par défaut. Les fenêtres circulaires (ex. 330 → 30) sont acceptées. |
| `surf_level_conditions_reference` | 1 ligne par niveau | Sheet « Ref - surf_level_conditions_ref » | Les CHECK imposent `min ≤ idéal min ≤ idéal max ≤ max` : un seuil mal saisi est refusé par la base elle-même. |
| `marine_forecast` | 1 ligne par spot et par heure | Open-Meteo + `tide.py` | Unicité `(spot_id, forecast_datetime)` : chaque collecte met à jour les heures existantes, sans doublon. |
| `spot_hour_scores` | 1 ligne par spot, heure et niveau | `score.py` | Les CHECK garantissent qu'un créneau non éligible a une raison et pas de score global. |

Les « enum » du doc sont des CHECK sur du texte plutôt que des types ENUM Postgres : ajouter une valeur revient à modifier une ligne.

**Sécurité.** Row Level Security est activé partout, avec une politique de lecture seule pour la clé publique (l'app Streamlit). Seuls les scripts écrivent, avec la clé secrète. Cette clé n'est jamais dans le code : elle vit dans `.env` en local (exclu de Git) et dans les *Secrets* GitHub pour l'automatisation.

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
| `is_daylight` | `sunrise`, `sunset` (données journalières) : l'heure commence entre le lever et le coucher du soleil | Weather |

- **Unités et conventions du doc :** heures en UTC (`timezone=GMT`), vent en km/h, directions en « d'où ça vient », comme les fenêtres du référentiel.
- **Fenêtre :** `past_days=1` et `forecast_days=8`. Le jour passé et le jour en plus servent à encadrer chaque heure utile par une basse mer et une pleine mer, nécessaires au calcul de la marée.
- **Sobriété :** une seule requête par API pour tous les spots (Open-Meteo accepte des listes de coordonnées), soit 2 appels par collecte. En cas d'échec : 3 essais avec attente croissante, puis un nouvel essai spot par spot.
- **Traçabilité :** `data_source` et `retrieved_at` sur chaque ligne. Le `forecast_retrieved_at` des scores pointe vers cette collecte.
- Le script sort en erreur si un spot échoue : le scoring n'est alors pas lancé, et l'app garde les derniers scores, avec leur date.

### 3. Marée : `tide.py`

Open-Meteo donne la hauteur d'eau, pas le stade de la marée. `tide.py` applique la section « Calcul de tide_stage » du doc v3 :

1. Repérer les basses et pleines mers (minima et maxima locaux de `sea_level_height_m`). Un palier de plusieurs heures à la même hauteur ne compte qu'une fois.
2. Entre deux extrêmes, calculer la progression de l'heure : `tide_level_pct` vaut 0 à la basse mer et 1 à la pleine mer, en montée comme en descente.
3. `tide_direction` vaut `montante` entre une basse et une pleine mer, `descendante` sinon. Une pleine mer est le début de la descente, une basse mer le début de la montée.
4. `tide_stage` : `basse` si pct < 0,3, `pleine` si pct > 0,7, `mi-maree` sinon.

Les quelques heures avant le premier extrême et après le dernier restent vides, car on ne peut pas les situer dans un cycle. Grâce à la marge J-1 et J+8, elles tombent hors de la fenêtre utile (J-1 à J+7).

### 4. Scores : `score.py`

Pour chaque spot, chaque heure de l'heure en cours à J+7 et chacun des 5 niveaux, `score.py` applique les sections « Éligibilité », « Calcul des sous-scores » et « Calcul du score global » du doc. Les scores sont précalculés pour tous les niveaux : l'app n'aura plus qu'à filtrer par niveau, distance, date et horaires.

**Éligibilité.** Un créneau est écarté, avec sa raison dans `ineligibility_reason`, si :

| Raison | Règle |
|---|---|
| `niveau_spot` | le niveau est inférieur au `min_level` du spot |
| `nuit` | l'heure commence avant le lever ou après le coucher du soleil (ajout par rapport au doc : les meilleurs créneaux tombaient souvent le soir, quand le vent tombe, mais de nuit) |
| `donnees_manquantes` | il manque la houle (hauteur, période, direction), le vent (vitesse, direction) ou la marée |
| `houle_trop_forte` | hauteur effective > `swell_height_max` du niveau |
| `houle_trop_faible` | hauteur effective < `swell_height_min` du niveau : mer plate pour ce niveau (ajout v1 : en v0, une houle de 0,18 m obtenait 60/100 grâce à la période, au vent et à la marée) |
| `vent_trop_fort` | vent > `wind_speed_max` du niveau |

**Sous-scores (0 à 100).** Toutes les rampes sont linéaires entre les seuils du référentiel par niveau.

| Sous-score | Calcul |
|---|---|
| Direction de houle | Écart entre la houle et la fenêtre idéale du spot (0 si elle est dedans). Facteur 1 dans la fenêtre, de 1 à 0,2 jusqu'à 60° d'écart, puis jusqu'à 0 à 90°. `swell_direction_score` = facteur × 100. |
| Houle | `hauteur effective = swell_height_m × facteur`, notée selon le niveau : 30 → 70 du min à l'idéal, 100 dans l'idéal, 100 → 40 jusqu'au max. Une grosse houle qui arrive de dos ne rend donc pas un spot dangereux : elle le rend plat (`houle_trop_faible`). |
| Période | 0 hors des bornes du niveau, 0 → 90 jusqu'à l'idéal, 100 dans l'idéal, 100 → 50 jusqu'au max |
| Vitesse du vent | 100 jusqu'à `wind_speed_ideal_max`, puis 100 → 0 jusqu'à `wind_speed_max` |
| Direction du vent | Écart à la fenêtre offshore du spot : 100 dedans, 100 → 70 jusqu'à 45° (side-offshore), 70 → 30 jusqu'à 90° (side), 30 → 0 au-delà (onshore). 100 si le vent fait moins de 5 km/h. |
| Vent | moyenne 50/50 de la vitesse et de la direction |
| Marée | `ideal_tide_stage` est traduit en plage de `tide_level_pct` (basse 0–0,35 ; mi-marée 0,3–0,7 ; pleine 0,65–1 ; montante ou descendante 0–1 avec un sens imposé). 100 dans la plage et dans le bon sens, 70 dans la plage mais à contre-sens, sinon 100 − 200 × l'écart à la plage. |

**Score global** = (0,40 × houle + 0,20 × période + 0,25 × vent + 0,15 × marée) × facteur vent de mer. Les poids sont ceux du doc. Le facteur vaut 1 si le vent est offshore ou faible, et descend jusqu'à 0,5 quand il souffle de la mer à 25 km/h ou plus : `1 − 0,5 × (1 − direction du vent / 100) × force`, la force allant de 0 à 10 km/h à 1 à 25 km/h. Un vent de mer soutenu hache les vagues, ce qu'une moyenne pondérée ne rend pas : en v0, 1,5 m avec 22 km/h plein onshore donnait 75 à un expert, contre 43 en v1. Tous les paramètres sont en tête de `score.py`, et chaque ligne garde la version utilisée (`scoring_version`).

**Calibration v1 (20/10).** Rejouée sur l'export du 18/10 (11 760 scores) avant d'être codée :

| Niveau | Éligibles v0 → v1 | Médiane v0 → v1 | ≥ 50 (seuil d'affichage) v0 → v1 |
|---|---|---|---|
| débutant | 88 → 67 | 75 → 71 | 83 % → 96 % |
| intermédiaire | 315 → 242 | 79 → 74 | 92 % → 88 % |
| avancé | 593 → 477 | 70 → 57 | 94 % → 58 % |
| expert | 792 → 676 | 71 → 48 | 98 % → 45 % |
| pro | 926 → 809 | 71 → 47 | 97 % → 39 % |

Les créneaux retirés sont des mers plates (459 lignes `houle_trop_faible`). Les scores baissent surtout pour les niveaux qui surfent par vent fort, souvent onshore cette semaine-là. Le débutant reste haut : ses créneaux éligibles sont des jours de petite houle et de vent faible. Les meilleurs créneaux ne bougent presque pas (Pors Carn lundi 15 h : 99 → 97 pour un avancé). Les seuils minimum de houle diffèrent selon le niveau (0,4 m pour un débutant, 0,6 m à partir d'avancé) : un créneau éligible pour un débutant peut donc être trop petit pour un avancé.

**Choix d'implémentation**
- Les fenêtres de houle et de vent du Sheet passent par le nord si besoin (ex. 330 → 30). Si un spot n'en a pas, le code les déduit de `spot_orientation_deg` : houle = orientation ± 30°, vent offshore = orientation + 180° ± 45°. Avec la fenêtre par défaut, le calcul de direction de houle donne exactement la table du doc (1 jusqu'à 30° de l'orientation, 0 au-delà de 120°).
- La table ne garde que la fenêtre en cours : chaque calcul met à jour les heures à venir et supprime les heures passées. `forecast_retrieved_at` indique la collecte utilisée.
- Les conditions (houle, vent, marée…) ne sont pas recopiées : l'app les lira par jointure sur `marine_forecast`.

Prévu en V2 : `tide_coefficient` (source SHOM), aujourd'hui vide, et `crowd_level`, stocké mais pas utilisé par l'algorithme.

### 5. Interface : `app.py`, `selection.py`, `explain.py`, `ui.py`

Sections « Processus de recommandation » (étape recherche utilisateur), « Sélection », « Sorties » et onglet « Interface utilisateur » du doc. Maquette : Figma « FindYourWave – Maquettes interface », planche C v2.

| Étape | Ce que fait le code |
|---|---|
| Lecture | Clé **publishable** (rôle `anon`, lecture seule). `spot_hour_scores` du niveau choisi, `marine_forecast` et `surf_spot_properties` sur les jours demandés, page par page, gardés en cache 10 min. |
| Filtres | Distance à vol d'oiseau depuis une liste de villes ; date et heure converties de l'UTC vers Europe/Paris ; un créneau compte s'il se termine avant l'heure de fin choisie. |
| Sélection | Par spot et par jour : heure au meilleur score, étendue aux heures consécutives à moins de 10 points. Score minimum 50, 5 résultats au plus, à égalité le spot le plus proche. |
| Explication | Les 2 plus fortes contributions (sous-score × poids), puis tout sous-score < 50 et le vent de mer s'il retire au moins 5 % du score. Le détail du score affiche les contributions et la pénalité de vent de mer : leur somme retombe sur le score global. |
| Absence de résultat | Raison principale par jour : aucun spot dans le rayon, pas de prévision, niveau, nuit ou horaires, houle trop faible ou trop forte, vent trop fort, conditions moyennes. |
| Fraîcheur | Date du dernier calcul (`scored_at`), bouton « Rafraîchir » (vide le cache, ne relance pas de collecte), alerte si les scores ont plus de 12 h. |

`selection.py` et `explain.py` sont du Python pur, testés sans Streamlit. Le module s'appelle `selection.py` et non `select.py`, car `select` est un module de la bibliothèque standard de Python.

## Qualité des données

Les trois requêtes de contrôle se lancent dans le SQL Editor de Supabase, en lecture seule. Résultats sur les données réelles :

| Requête | Ce qu'elle vérifie | Résultat |
|---|---|---|
| `003_checks.sql` | 14 spots tous renseignés et collectés, collecte de moins de 13 h, prévisions jusqu'à J+7, aucune heure manquante, aucune valeur vide sur la houle, le vent, les températures et la hauteur d'eau, valeurs plausibles, 3 stades de marée présents | 20 contrôles sur 20 OK |
| `004_null_columns.sql` | Taux de remplissage de chaque colonne | 100 % partout, sauf les 3 colonnes de marée (96 %, ce sont les heures de bord de fenêtre) et `tide_coefficient` (0 %, prévu en V2) |
| `005_tide_check.sql` | Le stade suit la règle du doc. L'eau monte bien quand la marée est montante et baisse quand elle est descendante. Les basses et pleines mers sont bien des creux et des pics. | 0 erreur. Environ 12,2 h entre deux basses mers, ce qui correspond au cycle semi-diurne réel (12 h 25). |

`006_scores_check.sql` contrôle ensuite les scores : une ligne par spot, heure et niveau, calcul de moins de 13 h fait sur la dernière collecte, aucun spot éligible sous son niveau minimum, et répartition des scores.

Les tests unitaires (`python -m pytest tests`, 40 tests) vérifient sans réseau la marée sur des courbes simulées, le rejet des dates parasites du Sheet, l'assemblage des lignes, chaque règle de scoring du doc, la sélection des créneaux (fuseau horaire, extension du créneau, top 5, raisons d'absence) et les explications (le détail affiché retombe bien sur le score global).

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
4. Scorer : `python score.py --dry-run` (aperçu dans `scores_preview.csv`), puis `python score.py`.
5. Contrôler : exécuter `sql/003_checks.sql` à `006_scores_check.sql`.
6. Interface : copier `.streamlit/secrets.toml.example` en `.streamlit/secrets.toml` (URL et clé **publishable**), puis `streamlit run app.py`. L'app s'ouvre sur `http://localhost:8501`.

**Automatisation.** Dans GitHub, **Settings → Secrets and variables → Actions** :
- *Secrets* (chiffrés, invisibles même dans les logs) : `SUPABASE_URL`, `SUPABASE_SECRET_KEY` ;
- *Variables* : `GID_SPOT_PROPERTIES`, `GID_SPOT_CONDITIONS`, `GID_LEVEL_CONDITIONS`.

Le workflow `collect` synchronise alors le Sheet, collecte les prévisions puis calcule les scores à 4 h, 11 h et 17 h UTC. Il peut aussi se lancer à la main depuis l'onglet **Actions**.
