"""Sélection des recommandations au moment de la recherche (sans Streamlit, sans base).

Le module s'appelle selection.py et non select.py : « select » est un module de Python.

Sections « Filtrage géographique », « Filtrage temporel », « Classement » et
« Sélection des recommandations » du doc :
- distance ville de départ -> spot <= distance max (à vol d'oiseau) ;
- date et heure en heure de Paris (forecast_datetime est en UTC) ;
- par spot et par jour : meilleur créneau, étendu aux heures consécutives dont le
  score reste >= score_max - 10 ;
- 5 résultats au maximum par jour, score minimum 50 ;
- sinon, la raison principale de l'absence de résultat.
"""
import datetime as dt
import math
from dataclasses import dataclass, field

import pandas as pd

from explain import fr_date, slot_label

TIMEZONE = "Europe/Paris"
MIN_SCORE = 50          # seuil d'affichage
MAX_RESULTS = 5         # par jour
SLOT_TOLERANCE = 10     # créneau étendu tant que le score reste >= score_max - 10

LEVEL_LABELS = {"debutant": "Débutant", "intermediaire": "Intermédiaire", "avance": "Avancé",
                "expert": "Expert", "pro": "Pro"}

# Villes de départ proposées (latitude, longitude du centre-ville)
CITIES = {
    "Auray": (47.6680, -2.9829), "Brest": (48.3904, -4.4861), "Carhaix-Plouguer": (48.2758, -3.5730),
    "Concarneau": (47.8753, -3.9189), "Douarnenez": (48.0925, -4.3290), "Guingamp": (48.5626, -3.1508),
    "Landerneau": (48.4508, -4.2494), "Lannion": (48.7326, -3.4566), "Lorient": (47.7483, -3.3700),
    "Morlaix": (48.5776, -3.8280), "Nantes": (47.2184, -1.5536), "Pontivy": (48.0680, -2.9628),
    "Quimper": (47.9960, -4.1024), "Quimperlé": (47.8728, -3.5498), "Rennes": (48.1173, -1.6778),
    "Saint-Brieuc": (48.5136, -2.7603), "Saint-Malo": (48.6493, -2.0257), "Vannes": (47.6582, -2.7608),
}

INELIGIBILITY_MESSAGES = {
    "houle_trop_faible": "Mer trop plate pour ton niveau ce jour-là.",
    "houle_trop_forte": "Houle trop forte pour ton niveau ce jour-là.",
    "vent_trop_fort": "Vent trop fort pour ton niveau ce jour-là.",
    "donnees_manquantes": "Prévisions incomplètes pour ce jour-là : impossible de calculer un score.",
}


@dataclass
class DayResult:
    day: dt.date
    recommendations: list[dict] = field(default_factory=list)
    reason: str | None = None    # code de la raison s'il n'y a aucun résultat
    message: str | None = None   # message affiché s'il n'y a aucun résultat
    best_score: int | None = None  # meilleur score du jour quand tout reste sous MIN_SCORE


# ---------------------------------------------------------------------------
# Distance
# ---------------------------------------------------------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance à vol d'oiseau, en km."""
    lat1, lon1, lat2, lon2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(a))


def spots_within(spots: pd.DataFrame, city: str, max_km: float) -> pd.DataFrame:
    """Spots (surf_spot_properties) à moins de max_km de la ville, avec la colonne distance_km."""
    lat, lon = CITIES[city]
    out = spots.copy()
    out["distance_km"] = [round(haversine_km(lat, lon, a, b))
                          for a, b in zip(out["localisation_lat"], out["localisation_lon"])]
    return out[out["distance_km"] <= max_km].sort_values("distance_km").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Heure locale
# ---------------------------------------------------------------------------
def with_local_time(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute local_date et local_hour (heure de Paris) à partir de forecast_datetime (UTC)."""
    out = df.copy()
    out["forecast_datetime"] = pd.to_datetime(out["forecast_datetime"], utc=True)
    local = out["forecast_datetime"].dt.tz_convert(TIMEZONE)
    out["local_date"] = local.dt.date
    out["local_hour"] = local.dt.hour
    return out


def utc_bounds(days: list[dt.date]) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Début du premier jour et fin du dernier jour (heure de Paris), en UTC, pour la requête."""
    start = pd.Timestamp(min(days)).tz_localize(TIMEZONE)
    end = pd.Timestamp(max(days) + dt.timedelta(days=1)).tz_localize(TIMEZONE)
    return start.tz_convert("UTC"), end.tz_convert("UTC")


# ---------------------------------------------------------------------------
# Meilleur créneau d'un spot
# ---------------------------------------------------------------------------
def best_slot(rows: pd.DataFrame) -> tuple[int, int, pd.Series]:
    """rows : heures éligibles et scorées d'un spot pour un jour (local_hour, global_score).
    Renvoie (heure de début, heure de fin exclue, ligne de l'heure au meilleur score)."""
    rows = rows.sort_values("local_hour")
    best = rows.loc[rows["global_score"].idxmax()]  # la plus tôt en cas d'égalité
    scores = dict(zip(rows["local_hour"], rows["global_score"]))
    floor = best["global_score"] - SLOT_TOLERANCE
    start = end = int(best["local_hour"])
    while scores.get(start - 1, -1) >= floor:
        start -= 1
    while scores.get(end + 1, -1) >= floor:
        end += 1
    return start, end + 1, best


# ---------------------------------------------------------------------------
# Recherche
# ---------------------------------------------------------------------------
def recommend_day(scores: pd.DataFrame, spots: pd.DataFrame, day: dt.date,
                  hour_from: int, hour_to: int) -> DayResult:
    """scores : lignes de spot_hour_scores du niveau (avec local_date / local_hour),
    spots : spots dans le rayon (spots_within). Une recherche, un jour."""
    result = DayResult(day)
    if spots.empty:
        result.reason = "aucun_spot_rayon"
        return result

    day_rows = scores[(scores["local_date"] == day) & scores["spot_id"].isin(spots["spot_id"])]
    if day_rows.empty:
        result.reason = "pas_de_prevision"
        return result
    if (day_rows["ineligibility_reason"] == "niveau_spot").all():
        result.reason = "niveau_spot"
        return result

    in_hours = day_rows[(day_rows["local_hour"] >= hour_from) & (day_rows["local_hour"] < hour_to)]
    if in_hours.empty:
        result.reason = "hors_horaires"
        return result
    if (in_hours["ineligibility_reason"] == "nuit").all():
        result.reason = "nuit"
        return result

    eligible = in_hours[in_hours["is_eligible"].astype(bool) & in_hours["global_score"].notna()]
    if eligible.empty:
        reasons = in_hours["ineligibility_reason"]
        reasons = reasons[~reasons.isin(["niveau_spot", "nuit"])]
        result.reason = reasons.mode().iloc[0] if not reasons.empty else "donnees_manquantes"
        return result

    info = spots.set_index("spot_id")
    candidates = []
    for spot_id, rows in eligible.groupby("spot_id"):
        start, end, best = best_slot(rows)
        hourly = {h: None for h in range(hour_from, hour_to)}
        hourly |= {int(h): round(s) for h, s in zip(rows["local_hour"], rows["global_score"])}
        spot = info.loc[spot_id]
        candidates.append({
            "spot_id": spot_id, "spot_name": spot["spot_name"], "department": spot.get("department"),
            "distance_km": int(spot["distance_km"]),
            "lat": float(spot["localisation_lat"]), "lon": float(spot["localisation_lon"]),
            "date": day, "start_hour": start, "end_hour": end, "slot": slot_label(start, end),
            "score": round(best["global_score"]), "best_datetime": best["forecast_datetime"],
            "scores": best.to_dict(), "hourly": hourly,
        })

    kept = sorted((c for c in candidates if c["scores"]["global_score"] >= MIN_SCORE),
                  key=lambda c: (-c["scores"]["global_score"], c["distance_km"]))[:MAX_RESULTS]
    if not kept:
        result.reason = "conditions_moyennes"
        result.best_score = round(max(c["scores"]["global_score"] for c in candidates))
        return result
    for rank, rec in enumerate(kept, start=1):
        rec["rank"] = rank
    result.recommendations = kept
    return result


def recommend(scores: pd.DataFrame, spots: pd.DataFrame, city: str, max_km: float,
              days: list[dt.date], hour_from: int, hour_to: int, level: str) -> list[DayResult]:
    """Recherche complète : un DayResult par jour, avec le message d'absence le cas échéant."""
    nearby = spots_within(spots, city, max_km)
    scores = with_local_time(scores) if "local_date" not in scores else scores
    results = []
    for day in days:
        res = recommend_day(scores, nearby, day, hour_from, hour_to)
        if res.reason:
            res.message = no_result_message(res, city=city, max_km=max_km, level=level,
                                            hour_from=hour_from, hour_to=hour_to)
        results.append(res)
    return results


def no_result_message(res: DayResult, city: str, max_km: float, level: str,
                      hour_from: int, hour_to: int) -> str:
    if res.reason == "aucun_spot_rayon":
        return f"Aucun spot à moins de {max_km:g} km de {city}. Augmente la distance maximale."
    if res.reason == "pas_de_prevision":
        return f"Pas encore de prévisions pour {fr_date(res.day)}."
    if res.reason == "niveau_spot":
        return f"Aucun spot de ce rayon n’est accessible au niveau {LEVEL_LABELS[level]}."
    if res.reason in ("hors_horaires", "nuit"):
        return (f"Aucun créneau de jour entre {slot_label(hour_from, hour_to)}. "
                "Élargis tes horaires.")
    if res.reason == "conditions_moyennes":
        return (f"Les conditions restent moyennes : meilleur score {res.best_score}/100, "
                f"sous le seuil de {MIN_SCORE}.")
    return INELIGIBILITY_MESSAGES.get(res.reason, "Aucun créneau ne correspond à ta recherche ce jour-là.")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
EXPORT_COLUMNS = ["date", "rang", "spot", "departement", "distance_km", "creneau", "score_global",
                  "score_houle", "score_periode", "score_vent", "score_maree", "houle_large", "houle_spot", "vent", "maree",
                  "eau", "explication", "remarques", "vigilance"]


def export_table(results: list[DayResult]) -> pd.DataFrame:
    """Une ligne par recommandation. Les clés 'conditions' (liste de (libellé, valeur)) et
    'explanation' (sortie de explain.explain) sont ajoutées par l'application."""
    rows = []
    for res in results:
        for rec in res.recommendations:
            cond = dict(rec.get("conditions", []))
            exp = rec.get("explanation", {})
            s = rec["scores"]
            rows.append({
                "date": rec["date"].isoformat(), "rang": rec["rank"], "spot": rec["spot_name"],
                "departement": rec["department"], "distance_km": rec["distance_km"], "creneau": rec["slot"],
                "score_global": rec["score"], "score_houle": s.get("swell_score"),
                "score_periode": s.get("period_score"), "score_vent": s.get("wind_score"),
                "score_maree": s.get("tide_score"), "houle_large": cond.get("Houle au large", cond.get("Houle")),
                "houle_spot": cond.get("Houle sur le spot"), "vent": cond.get("Vent"),
                "maree": cond.get("Marée"), "eau": cond.get("Eau"),
                "explication": exp.get("summary"), "remarques": " ".join(exp.get("remarks", [])),
                "vigilance": " ".join(exp.get("warnings", [])),
            })
    return pd.DataFrame(rows, columns=EXPORT_COLUMNS)
