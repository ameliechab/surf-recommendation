"""marine_forecast + référentiels -> table spot_hour_scores.

Pour chaque spot, chaque heure de prévision (de l'heure en cours à J+7) et
chaque niveau : éligibilité, sous-scores et score global, selon les sections
« Calcul des sous-scores » et « Calcul du score global » du doc.

Usage :
    python score.py              # calcule et écrit dans Supabase
    python score.py --dry-run    # calcule et enregistre scores_preview.csv, sans écrire en base
"""
import argparse
import datetime as dt
import sys

import pandas as pd

import db

SCORING_VERSION = "v1"
HORIZON_HOURS = 168  # 7 jours de scores à partir de l'heure en cours

# Poids du doc (inchangés en v1)
WEIGHTS = {"swell": 0.40, "period": 0.20, "wind": 0.25, "tide": 0.15}
WIND_WEIGHTS = {"speed": 0.5, "direction": 0.5}

# Calibration v1 (20/10)
SCORE_FLOOR = 0  # période hors plage du niveau, vent au max du niveau (30 en v0)
ONSHORE_MAX_PENALTY = 0.5  # le score global perd jusqu'à 50 % avec un vent de mer soutenu
ONSHORE_WIND_KMH = (10, 25)  # la pénalité monte de 0 à 100 % entre ces deux vitesses

# Fenêtres par défaut quand le Sheet n'en donne pas (autour de spot_orientation_deg)
DEFAULT_SWELL_HALF_WIDTH = 30
DEFAULT_WIND_HALF_WIDTH = 45
CALM_WIND_KMH = 5  # en dessous, la direction du vent ne compte plus

LEVELS = ["debutant", "intermediaire", "avance", "expert", "pro"]

# Traduction de ideal_tide_stage (Sheet) en plage de tide_level_pct et sens
TIDE_TARGETS = {
    "basse": (0.0, 0.35, "toutes"),
    "mi-maree": (0.3, 0.7, "toutes"),
    "pleine": (0.65, 1.0, "toutes"),
    "montante": (0.0, 1.0, "montante"),
    "descendante": (0.0, 1.0, "descendante"),
    "toutes": (0.0, 1.0, "toutes"),
}

SCORE_COLUMNS = ["swell_height_score", "swell_direction_score", "swell_score", "period_score",
                 "wind_speed_score", "wind_direction_score", "wind_score", "tide_score", "global_score"]

REQUIRED = ["swell_height_m", "swell_period_s", "swell_direction_deg",
            "wind_speed_kmh", "wind_direction_deg", "tide_level_pct", "tide_direction"]


# ---------------------------------------------------------------------------
# Outils
# ---------------------------------------------------------------------------
def interpolate(x, x0, x1, y0, y1):
    """Valeur linéaire entre (x0, y0) et (x1, y1), bornée aux extrémités."""
    if x1 == x0:
        return y1
    t = min(max((x - x0) / (x1 - x0), 0.0), 1.0)
    return y0 + t * (y1 - y0)


def angular_distance(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def distance_to_window(direction, low, high):
    """0 si la direction est dans la fenêtre [low, high], sinon l'écart à la borne
    la plus proche. Gère les fenêtres qui passent par le nord (ex. 330 -> 30)."""
    if (direction - low) % 360 <= (high - low) % 360:
        return 0.0
    return min(angular_distance(direction, low), angular_distance(direction, high))


def window(low, high, orientation, offset, half_width):
    """Fenêtre du Sheet, ou fenêtre par défaut autour de l'orientation du spot."""
    if low is not None and high is not None:
        return low, high
    center = (orientation + offset) % 360
    return (center - half_width) % 360, (center + half_width) % 360


# ---------------------------------------------------------------------------
# Sous-scores (0-100)
# ---------------------------------------------------------------------------
def swell_direction_factor(gap):
    """Écart hors de la fenêtre de houle -> facteur appliqué à la hauteur."""
    if gap <= 60:
        return interpolate(gap, 0, 60, 1.0, 0.2)
    return interpolate(gap, 60, 90, 0.2, 0.0)


def height_score(h, ref):
    if h < ref["swell_height_min"]:
        return interpolate(h, 0, ref["swell_height_min"], 0, 30)
    if h < ref["swell_height_ideal_min"]:
        return interpolate(h, ref["swell_height_min"], ref["swell_height_ideal_min"], 30, 70)
    if h <= ref["swell_height_ideal_max"]:
        return 100.0
    return interpolate(h, ref["swell_height_ideal_max"], ref["swell_height_max"], 100, 40)


def period_score(p, ref):
    if p < ref["period_min"] or p > ref["period_max"]:
        return float(SCORE_FLOOR)
    if p < ref["period_ideal_min"]:
        return interpolate(p, ref["period_min"], ref["period_ideal_min"], SCORE_FLOOR, 90)
    if p <= ref["period_ideal_max"]:
        return 100.0
    return interpolate(p, ref["period_ideal_max"], ref["period_max"], 100, 50)


def wind_speed_score(v, ref):
    if v <= ref["wind_speed_ideal_max"]:
        return 100.0
    return interpolate(v, ref["wind_speed_ideal_max"], ref["wind_speed_max"], 100, SCORE_FLOOR)


def wind_direction_score(gap, speed):
    if speed <= CALM_WIND_KMH:
        return 100.0
    if gap <= 45:
        return interpolate(gap, 0, 45, 100, 70)
    if gap <= 90:
        return interpolate(gap, 45, 90, 70, 30)
    return interpolate(gap, 90, 180, 30, 0)


def onshore_factor(direction_score, speed):
    """Facteur appliqué au score global : un vent de mer (ou de travers) soutenu
    hache les vagues, quels que soient la houle et la marée. 1 si le vent est
    offshore ou faible, jusqu'à 1 - ONSHORE_MAX_PENALTY si plein onshore et fort."""
    strength = interpolate(speed, *ONSHORE_WIND_KMH, 0, 1)
    return 1 - ONSHORE_MAX_PENALTY * (1 - direction_score / 100) * strength


def tide_score(pct, direction, ideal_stage):
    low, high, ideal_direction = TIDE_TARGETS[ideal_stage or "toutes"]
    if low <= pct <= high:
        return 100.0 if ideal_direction in ("toutes", direction) else 70.0
    gap = low - pct if pct < low else pct - high
    return max(0.0, 100 - 200 * gap)


# ---------------------------------------------------------------------------
# Une heure, un spot, un niveau
# ---------------------------------------------------------------------------
def score_hour(fc: dict, spot: dict, level: str, ref: dict) -> dict:
    row = {"spot_id": fc["spot_id"], "forecast_datetime": fc["forecast_datetime"], "surf_level": level,
           "is_eligible": False, "ineligibility_reason": None,
           "scoring_version": SCORING_VERSION, "forecast_retrieved_at": fc["retrieved_at"]}
    row |= dict.fromkeys(SCORE_COLUMNS)  # vides tant que le créneau n'est pas éligible

    if LEVELS.index(level) < LEVELS.index(spot["min_level"]):
        return row | {"ineligibility_reason": "niveau_spot"}
    if fc.get("is_daylight") is False:
        return row | {"ineligibility_reason": "nuit"}
    if any(fc.get(c) is None for c in REQUIRED):
        return row | {"ineligibility_reason": "donnees_manquantes"}

    # Houle : la hauteur est réduite quand la houle arrive hors de la fenêtre du spot
    low, high = window(spot["ideal_swell_orientation_min"], spot["ideal_swell_orientation_max"],
                       spot["spot_orientation_deg"], 0, DEFAULT_SWELL_HALF_WIDTH)
    factor = swell_direction_factor(distance_to_window(fc["swell_direction_deg"], low, high))
    effective_height = fc["swell_height_m"] * factor
    if effective_height > ref["swell_height_max"]:
        return row | {"ineligibility_reason": "houle_trop_forte"}
    if effective_height < ref["swell_height_min"]:
        return row | {"ineligibility_reason": "houle_trop_faible"}  # mer plate pour ce niveau
    if fc["wind_speed_kmh"] > ref["wind_speed_max"]:
        return row | {"ineligibility_reason": "vent_trop_fort"}

    swell = height_score(effective_height, ref)
    period = period_score(fc["swell_period_s"], ref)

    # Vent : fenêtre offshore du Sheet, ou face à la mer + 180°
    low, high = window(spot["ideal_wind_orientation_min"], spot["ideal_wind_orientation_max"],
                       spot["spot_orientation_deg"], 180, DEFAULT_WIND_HALF_WIDTH)
    speed = wind_speed_score(fc["wind_speed_kmh"], ref)
    direction = wind_direction_score(distance_to_window(fc["wind_direction_deg"], low, high),
                                     fc["wind_speed_kmh"])
    wind = WIND_WEIGHTS["speed"] * speed + WIND_WEIGHTS["direction"] * direction

    tide = tide_score(fc["tide_level_pct"], fc["tide_direction"], spot["ideal_tide_stage"])

    total = (WEIGHTS["swell"] * swell + WEIGHTS["period"] * period
             + WEIGHTS["wind"] * wind + WEIGHTS["tide"] * tide)
    total *= onshore_factor(direction, fc["wind_speed_kmh"])

    scores = {"swell_height_score": swell, "swell_direction_score": factor * 100, "swell_score": swell,
              "period_score": period, "wind_speed_score": speed, "wind_direction_score": direction,
              "wind_score": wind, "tide_score": tide, "global_score": total}
    return row | {"is_eligible": True} | {k: round(v, 1) for k, v in scores.items()}


def score_all(forecasts: list[dict], spots: dict, levels: dict) -> list[dict]:
    rows = []
    for fc in forecasts:
        spot = spots.get(fc["spot_id"])
        if spot is None:
            continue
        for level in LEVELS:
            rows.append(score_hour(fc, spot, level, levels[level]))
    return rows


# ---------------------------------------------------------------------------
# Lecture Supabase
# ---------------------------------------------------------------------------
def fetch_all(query, page_size=1000) -> list[dict]:
    """Supabase renvoie au plus 1000 lignes par requête : on lit page par page."""
    rows, start = [], 0
    while True:
        page = query.range(start, start + page_size - 1).execute().data
        rows += page
        if len(page) < page_size:
            return rows
        start += page_size


def to_float(row: dict, columns) -> dict:
    return row | {c: None if row[c] is None else float(row[c]) for c in columns}


def load_inputs(client, start: dt.datetime, end: dt.datetime):
    props = {r["spot_id"]: r for r in client.table("surf_spot_properties")
             .select("spot_id, spot_orientation_deg").execute().data}
    spots = {}
    for c in client.table("surf_spot_conditions_reference").select("*").execute().data:
        if c["spot_id"] in props:
            spots[c["spot_id"]] = c | props[c["spot_id"]]

    level_columns = ["swell_height_min", "swell_height_ideal_min", "swell_height_ideal_max", "swell_height_max",
                     "period_min", "period_ideal_min", "period_ideal_max", "period_max",
                     "wind_speed_ideal_max", "wind_speed_max"]
    levels = {r["surf_level"]: to_float(r, level_columns)
              for r in client.table("surf_level_conditions_reference").select("*").execute().data}

    forecasts = fetch_all(
        client.table("marine_forecast")
        .select("spot_id, forecast_datetime, retrieved_at, is_daylight, " + ", ".join(REQUIRED))
        .gte("forecast_datetime", start.isoformat())
        .lt("forecast_datetime", end.isoformat())
        .order("spot_id").order("forecast_datetime")
    )
    numeric = [c for c in REQUIRED if c != "tide_direction"]
    return [to_float(f, numeric) for f in forecasts], spots, levels


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="n'écrit pas en base, enregistre scores_preview.csv")
    args = parser.parse_args()

    client = db.get_client()
    start = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    end = start + dt.timedelta(hours=HORIZON_HOURS)
    forecasts, spots, levels = load_inputs(client, start, end)

    missing_levels = [lvl for lvl in LEVELS if lvl not in levels]
    if missing_levels:
        sys.exit(f"Niveaux absents de surf_level_conditions_reference : {', '.join(missing_levels)}")
    if not forecasts:
        sys.exit("Aucune prévision à scorer dans marine_forecast : lance d'abord collect.py.")

    rows = score_all(forecasts, spots, levels)
    scored_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows = [r | {"scored_at": scored_at} for r in rows]

    summary = pd.DataFrame(rows)
    eligible = summary[summary["is_eligible"]]
    print(f"{len(rows)} lignes ({summary['spot_id'].nunique()} spots × {summary['forecast_datetime'].nunique()} h × 5 niveaux)")
    print(f"Éligibles : {len(eligible)} ; raisons de non-éligibilité : "
          f"{summary['ineligibility_reason'].value_counts().to_dict()}")
    if len(eligible):
        print("Score global moyen par niveau : "
              f"{eligible.groupby('surf_level')['global_score'].mean().round(1).to_dict()}")

    if args.dry_run:
        summary.to_csv("scores_preview.csv", index=False)
        print("Aperçu enregistré dans scores_preview.csv (rien n'a été écrit en base).")
        return

    db.upsert(client, "spot_hour_scores", rows, on_conflict="spot_id,forecast_datetime,surf_level")
    # La table ne garde que la fenêtre en cours : les heures passées sont retirées
    client.table("spot_hour_scores").delete().lt("forecast_datetime", start.isoformat()).execute()
    print("Scores écrits dans spot_hour_scores.")


if __name__ == "__main__":
    main()
