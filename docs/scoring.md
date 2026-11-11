# Scoring

Comment chaque spot est noté, heure par heure, pour chacun des 5 niveaux : éligibilité, sous-scores, score global et calibration sur des données réelles.

## `score.py`

Pour chaque spot, chaque heure de l'heure en cours à J+7 et chacun des 5 niveaux, `score.py` applique les sections « Éligibilité », « Calcul des sous-scores » et « Calcul du score global » du doc. Les scores sont précalculés pour tous les niveaux : l'app n'aura plus qu'à filtrer par niveau, distance, date et horaires.

**Éligibilité.** Un créneau est écarté, avec sa raison dans `ineligibility_reason`, si :

| Raison | Règle |
|---|---|
| `niveau_spot` | le niveau est inférieur au `min_level` du spot |
| `nuit` | l'heure commence avant le lever ou après le coucher du soleil (ajout par rapport au doc : les meilleurs créneaux tombaient souvent le soir, quand le vent tombe, mais de nuit) |
| `donnees_manquantes` | il manque la houle (hauteur, période, direction), le vent (vitesse, direction) ou la marée |
| `houle_trop_forte` | hauteur effective (hauteur utile sur le spot) > `swell_height_max` du niveau |
| `houle_trop_faible` | hauteur effective < `swell_height_min` du niveau : mer plate pour ce niveau (ajout v1 : en v0, une houle de 0,18 m obtenait 60/100 grâce à la période, au vent et à la marée) |
| `vent_trop_fort` | vent > `wind_speed_max` du niveau |

**Sous-scores (0 à 100).** Toutes les rampes sont linéaires entre les seuils du référentiel par niveau.

| Sous-score | Calcul |
|---|---|
| Direction de houle | Écart entre la houle et la fenêtre idéale du spot (0 si elle est dedans). Facteur 1 dans la fenêtre, de 1 à 0,2 jusqu'à 60° d'écart, puis jusqu'à 0 à 90°. `swell_direction_score` = facteur × 100. |
| Houle | `hauteur effective = swell_height_m × facteur × swell_exposure`, notée selon le niveau : 30 → 70 du min à l'idéal, 100 dans l'idéal, 100 → 40 jusqu'au max. Une grosse houle qui arrive de dos ne rend donc pas un spot dangereux : elle le rend plat (`houle_trop_faible`). |
| Période | 0 hors des bornes du niveau, 0 → 90 jusqu'à l'idéal, 100 dans l'idéal, 100 → 50 jusqu'au max |
| Vitesse du vent | 100 jusqu'à `wind_speed_ideal_max`, puis 100 → 0 jusqu'à `wind_speed_max` |
| Direction du vent | Écart à la fenêtre offshore du spot : 100 dedans, 100 → 70 jusqu'à 45° (side-offshore), 70 → 30 jusqu'à 90° (side), 30 → 0 au-delà (onshore). 100 si le vent fait moins de 5 km/h. |
| Vent | moyenne 50/50 de la vitesse et de la direction |
| Marée | `ideal_tide_stage` est traduit en plage de `tide_level_pct` (basse 0–0,35 ; mi-marée 0,3–0,7 ; pleine 0,65–1 ; montante ou descendante 0–1 avec un sens imposé). 100 dans la plage et dans le bon sens, 70 dans la plage mais à contre-sens, sinon 100 − 200 × l'écart à la plage. |

**Score global** = (0,40 × houle + 0,20 × période + 0,25 × vent + 0,15 × marée) × facteur vent de mer. Les poids sont ceux du doc. Le facteur vaut 1 si le vent est offshore ou faible, et descend jusqu'à 0,5 quand il souffle de la mer à 25 km/h ou plus : `1 − 0,5 × (1 − direction du vent / 100) × force`, la force allant de 0 à 10 km/h à 1 à 25 km/h. Un vent de mer soutenu hache les vagues, ce qu'une moyenne pondérée ne rend pas : en v0, 1,5 m avec 22 km/h plein onshore donnait 75 à un expert, contre 43 en v1. Tous les paramètres sont en tête de `score.py`, et chaque ligne garde la version utilisée (`scoring_version`).

**Coefficient d'abri (v1.1, 11/11).** La houle d'Open-Meteo est celle du large : la grille du modèle de vagues a un pas d'environ 9 km. Dans une baie protégée, les vagues sont plus petites, même quand la houle arrive dans la bonne direction, et la fenêtre de houle ne peut pas le rendre (elle ne réduit la hauteur que hors de la fenêtre). `swell_exposure`, dans l'onglet conditions du Sheet, donne la part de la houle du large qui atteint le spot : 1 ou vide pour un spot exposé, 0,5 pour la plage d'Agadir (abritée par le port), 0,7 pour The Bay à Imsouane et pour Hash Point. Les spots retenus sont ceux que plusieurs sources décrivent comme abrités (surf-forecast.com, surfspot.it, guides locaux) ; les valeurs sont des estimations, à ajuster en comparant aux vagues observées. Les 14 spots bretons sont décrits comme exposés : 1.

L'effet n'est pas une simple baisse de note : les hauteurs deviennent plus réalistes. Rejoué sur les prévisions du 11/11, meilleur créneau de jour :

| Spot, niveau | 12/11 (2 à 2,4 m au large) | 14/11 (environ 1 m) | 16/11 (environ 0,5 m) |
|---|---|---|---|
| Agadir, débutant | exclu (trop fort) → 81 | 89 → 97 | 94 → exclu (trop petit) |
| Agadir, intermédiaire | exclu (trop fort) → 91 | 95 → exclu (trop petit) | 80 → exclu (trop petit) |
| The Bay, débutant | exclu (trop fort) → 65 | exclu (trop fort) → 87 | 89 → 89 |
| The Bay, intermédiaire | 77 → 98 | 90 → 100 | 84 → 84 |
| Hash Point, intermédiaire | 78 → 95 | 87 → 87 | 82 → exclu (trop petit) |

Ces spots ressortent donc les jours de grosse houle, quand les plages exposées sont trop fortes, et disparaissent par petite houle. C'est leur usage réel. Les scores portent `scoring_version = 'v1.1'`.

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

[← Retour au README](../README.md)
