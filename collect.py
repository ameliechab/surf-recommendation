"""Open-Meteo (Marine + Weather) -> table marine_forecast.

Pour chaque spot de surf_spot_properties : récupère les prévisions horaires
(past_days=1, forecast_days=8), calcule la marée, puis fait un upsert sur
(spot_id, forecast_datetime).

Usage :
    python collect.py               # collecte et écrit dans Supabase
    python collect.py --dry-run     # collecte et enregistre un CSV, sans écrire en base
    python collect.py --spot la_torche
"""
import argparse
import datetime as dt
import sys
import time

import pandas as pd
import requests

import config
import db
from tide import compute_tide

MARINE_FIELDS = {  # champ Open-Meteo -> colonne marine_forecast
    "swell_wave_height": "swell_height_m",
    "swell_wave_period": "swell_period_s",
    "swell_wave_direction": "swell_direction_deg",
    "sea_surface_temperature": "water_temp_c",
    "sea_level_height_msl": "sea_level_height_m",
}
WEATHER_FIELDS = {
    "wind_speed_10m": "wind_speed_kmh",
    "wind_direction_10m": "wind_direction_deg",
    "temperature_2m": "air_temp_c",
    "uv_index": "uv_index",
    "precipitation": "precipitation_mm",
}


PAUSE_BETWEEN_CALLS_S = 2  # pour ne pas solliciter Open-Meteo trop vite


def _get_json(url: str, params: dict):
    for attempt in range(3):
        try:
            # Open-Meteo répond parfois lentement : 10 s pour se connecter, 90 s pour répondre
            resp = requests.get(url, params=params, timeout=(10, 90))
            if resp.status_code == 200:
                return resp.json()
            error = f"HTTP {resp.status_code} : {resp.text[:200]}"
        except requests.RequestException as exc:
            error = str(exc)
        time.sleep(5 * 3 ** attempt)  # 5 s, 15 s, 45 s
    raise RuntimeError(f"{url} : {error}")


def _to_df(payload: dict, fields: dict) -> pd.DataFrame:
    df = pd.DataFrame(payload["hourly"]).rename(columns=fields)
    df["forecast_datetime"] = pd.to_datetime(df.pop("time"), utc=True)
    return df


def fetch_hourly(url: str, spots: list[dict], fields: dict, extra: dict | None = None) -> dict:
    """Une seule requête pour plusieurs spots (Open-Meteo accepte des listes de
    coordonnées). Renvoie {spot_id: DataFrame horaire}."""
    params = {
        "latitude": ",".join(str(s["localisation_lat"]) for s in spots),
        "longitude": ",".join(str(s["localisation_lon"]) for s in spots),
        "hourly": ",".join(fields),
        "past_days": config.PAST_DAYS,
        "forecast_days": config.FORECAST_DAYS,
        "timezone": "GMT",
        **(extra or {}),
    }
    payload = _get_json(url, params)
    if isinstance(payload, dict):  # un seul spot : Open-Meteo renvoie un objet, pas une liste
        payload = [payload]
    return {s["spot_id"]: _to_df(p, fields) for s, p in zip(spots, payload)}


def build_rows(spot_id: str, marine: pd.DataFrame, weather: pd.DataFrame, retrieved_at: str) -> list[dict]:
    df = marine.merge(weather, on="forecast_datetime", how="outer").sort_values("forecast_datetime")
    levels = [None if pd.isna(v) else float(v) for v in df["sea_level_height_m"]]
    df["tide_level_pct"], df["tide_direction"], df["tide_stage"] = compute_tide(levels)
    df["spot_id"] = spot_id
    df["data_source"] = config.DATA_SOURCE
    df["retrieved_at"] = retrieved_at
    df["forecast_datetime"] = df["forecast_datetime"].map(lambda t: t.isoformat())
    df = df.astype(object).where(df.notna(), None)
    return df.to_dict("records")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="n'écrit pas en base, enregistre forecast_preview.csv")
    parser.add_argument("--spot", help="ne collecter qu'un spot (spot_id)")
    args = parser.parse_args()

    client = db.get_client()
    query = client.table("surf_spot_properties").select("spot_id, localisation_lat, localisation_lon")
    if args.spot:
        query = query.eq("spot_id", args.spot)
    spots = query.execute().data
    if not spots:
        sys.exit("Aucun spot dans surf_spot_properties : lance d'abord sync_sheets.py.")

    retrieved_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    all_rows = []

    def collect(batch: list[dict]) -> list[dict]:
        """Collecte un groupe de spots ; renvoie les spots en échec."""
        try:
            marine = fetch_hourly(config.MARINE_API_URL, batch, MARINE_FIELDS)
            time.sleep(PAUSE_BETWEEN_CALLS_S)
            weather = fetch_hourly(config.WEATHER_API_URL, batch, WEATHER_FIELDS, {"wind_speed_unit": "kmh"})
        except Exception as exc:
            print(f"{', '.join(s['spot_id'] for s in batch)} : ERREUR {exc}", file=sys.stderr)
            return batch
        for spot in batch:
            spot_id = spot["spot_id"]
            rows = build_rows(spot_id, marine[spot_id], weather[spot_id], retrieved_at)
            if not args.dry_run:
                db.upsert(client, "marine_forecast", rows, on_conflict="spot_id,forecast_datetime")
            all_rows.extend(rows)
            no_tide = sum(r["tide_stage"] is None for r in rows)
            print(f"{spot_id} : {len(rows)} heures ({no_tide} sans marée)")
        return []

    # 1er passage : tous les spots en une requête par API (2 appels au total)
    failed = collect(spots)

    # Si ça échoue : pause, puis un spot à la fois, en douceur
    if failed:
        print("Nouvel essai spot par spot dans 60 s")
        time.sleep(60)
        retry = failed
        failed = []
        for spot in retry:
            failed += collect([spot])
            time.sleep(PAUSE_BETWEEN_CALLS_S)

    if args.dry_run and all_rows:
        pd.DataFrame(all_rows).to_csv("forecast_preview.csv", index=False)
        print("Aperçu enregistré dans forecast_preview.csv (rien n'a été écrit en base).")

    if failed:
        # code de sortie 1 : GitHub Actions ne lancera pas le scoring
        sys.exit(f"Collecte en échec pour : {', '.join(s['spot_id'] for s in failed)}")


if __name__ == "__main__":
    main()
