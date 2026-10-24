"""Tests hors ligne de la sélection : python -m pytest tests"""
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import selection  # noqa: E402

DAY = dt.date(2026, 10, 20)  # heure d'été : Paris = UTC + 2
SPOTS = pd.DataFrame([
    {"spot_id": "loch_guidel", "spot_name": "Le Loc'h", "department": "Morbihan",
     "localisation_lat": 47.7558, "localisation_lon": -3.5181},
    {"spot_id": "la_torche", "spot_name": "La Torche", "department": "Finistère",
     "localisation_lat": 47.8432, "localisation_lon": -4.3476},
    {"spot_id": "trestel", "spot_name": "Baie de Trestel", "department": "Côtes-d'Armor",
     "localisation_lat": 48.8198, "localisation_lon": -3.3530},
])


def rows(spot_id, scores, day=DAY, first_hour=9, reason=None):
    """Lignes de spot_hour_scores : scores heure par heure (heure de Paris), None = non éligible."""
    out = []
    for i, s in enumerate(scores):
        local = pd.Timestamp(dt.datetime.combine(day, dt.time(first_hour + i))).tz_localize("Europe/Paris")
        out.append({"spot_id": spot_id, "forecast_datetime": local.tz_convert("UTC").isoformat(),
                    "is_eligible": s is not None, "global_score": s,
                    "ineligibility_reason": None if s is not None else (reason or "houle_trop_faible"),
                    "swell_score": s, "period_score": s, "wind_score": s, "tide_score": s})
    return out


def search(score_rows, city="Lorient", max_km=100, hours=(8, 20), days=(DAY,), level="intermediaire"):
    return selection.recommend(pd.DataFrame(score_rows), SPOTS, city, max_km, list(days), *hours, level)


def test_distance():
    assert round(selection.haversine_km(*selection.CITIES["Lorient"], 47.7558, -3.5181)) == 11
    nearby = selection.spots_within(SPOTS, "Lorient", 100)
    assert list(nearby["spot_id"]) == ["loch_guidel", "la_torche"]  # Trestel est à 119 km
    assert list(nearby["distance_km"]) == [11, 74]


def test_local_time_and_bounds():
    df = selection.with_local_time(pd.DataFrame([{"forecast_datetime": "2026-10-20T07:00:00+00:00"}]))
    assert df["local_hour"].iloc[0] == 9 and df["local_date"].iloc[0] == DAY
    start, end = selection.utc_bounds([DAY, DAY + dt.timedelta(days=1)])
    assert start.isoformat() == "2026-10-19T22:00:00+00:00" and end.isoformat() == "2026-10-21T22:00:00+00:00"


def test_best_slot_is_extended_to_consecutive_hours_within_10_points():
    # 9 h : 70, 10 h : 82, 11 h : 90, 12 h : 85, 13 h : 79, 14 h : 88 -> 10 h – 13 h
    res = search(rows("loch_guidel", [70, 82, 90, 85, 79, 88]))[0]
    rec = res.recommendations[0]
    assert (rec["start_hour"], rec["end_hour"], rec["slot"], rec["score"]) == (10, 13, "10 h – 13 h", 90)
    # une heure non éligible coupe le créneau
    rec = search(rows("loch_guidel", [88, None, 90, 89]))[0].recommendations[0]
    assert (rec["start_hour"], rec["end_hour"]) == (11, 13)
    # la bande horaire couvre les horaires choisis, vide hors éligibilité
    assert rec["hourly"][8] is None and rec["hourly"][10] is None and rec["hourly"][11] == 90


def test_hours_filter_excludes_the_slot_ending_after_hour_to():
    res = search(rows("loch_guidel", [60, 95]), hours=(8, 10))[0]  # 9 h gardée, 10 h exclue
    assert res.recommendations[0]["slot"] == "9 h – 10 h"


def test_ranking_threshold_and_ties():
    score_rows = rows("loch_guidel", [80]) + rows("la_torche", [80]) + rows("trestel", [99])
    res = search(score_rows)[0]
    # Trestel hors rayon ; égalité 80 / 80 -> le plus proche d'abord
    assert [r["spot_id"] for r in res.recommendations] == ["loch_guidel", "la_torche"]
    assert [r["rank"] for r in res.recommendations] == [1, 2]
    low = search(rows("loch_guidel", [45, 48]))[0]
    assert low.recommendations == [] and low.reason == "conditions_moyennes"
    assert low.message == "Les conditions restent moyennes : meilleur score 48/100, sous le seuil de 50."


def test_at_most_five_results():
    many = pd.concat([SPOTS.assign(spot_id=SPOTS["spot_id"] + str(i)) for i in range(3)])
    score_rows = [r for sid in many["spot_id"] for r in rows(sid, [60 + len(sid)])]
    res = selection.recommend(pd.DataFrame(score_rows), many, "Lorient", 300, [DAY], 8, 20, "pro")[0]
    assert len(res.recommendations) == 5


def test_no_result_reasons():
    assert search(rows("loch_guidel", [90]), city="Rennes", max_km=30)[0].message == (
        "Aucun spot à moins de 30 km de Rennes. Augmente la distance maximale.")
    assert search(rows("loch_guidel", [90]), days=[DAY + dt.timedelta(days=1)])[0].message == (
        "Pas encore de prévisions pour mercredi 21 octobre.")
    assert search(rows("loch_guidel", [None], reason="niveau_spot"), level="debutant")[0].message == (
        "Aucun spot de ce rayon n’est accessible au niveau Débutant.")
    night = rows("loch_guidel", [None, None], first_hour=6, reason="nuit")
    assert search(night, hours=(6, 8))[0].message == "Aucun créneau de jour entre 6 h – 8 h. Élargis tes horaires."
    flat = rows("loch_guidel", [None, None]) + rows("la_torche", [None], reason="vent_trop_fort")
    assert search(flat)[0].message == "Mer trop plate pour ton niveau ce jour-là."


def test_export_table():
    res = search(rows("loch_guidel", [90]))
    rec = res[0].recommendations[0]
    rec["conditions"] = [("Houle au large", "0,8 m, 11 s d’ouest"), ("Houle sur le spot", "0,8 m, bien orientée"),
                         ("Vent", "9 km/h du nord")]
    rec["explanation"] = {"summary": "Houle idéale.", "warnings": ["Marée peu favorable."]}
    table = selection.export_table(res)
    assert list(table.columns) == selection.EXPORT_COLUMNS
    row = table.iloc[0]
    assert (row["spot"], row["creneau"], row["score_global"], row["houle_large"]) == (
        "Le Loc'h", "9 h – 10 h", 90, "0,8 m, 11 s d’ouest")
    assert row["houle_spot"] == "0,8 m, bien orientée" and row["vigilance"] == "Marée peu favorable."
