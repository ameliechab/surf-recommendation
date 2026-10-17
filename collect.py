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


def fetch_hourly(url: str, lat: float, lon: float, fields: dict, extra: dict | None = None) -> pd.DataFrame:
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": ",".join(fields),
        "past_days": config.PAST_DAYS,
        "forecast_days": config.FORECAST_DAYS,
        "timezone": "GMT",
        **(extra or {}),
    }
    for attempt in range(4):
        try:
            resp = requests.get(url, params=params, timeout=30)
            if resp.status_code == 200:
                break
            error = f"HTTP {resp.status_code} : {resp.text[:200]}"
        except requests.RequestException as exc:
            error = str(exc)
        time.sleep(2 ** (attempt + 1))
    else:
        raise RuntimeError(f"{url} : {error}")

    hourly = resp.json()["hourly"]
    df = pd.DataFrame(hourly).rename(columns=fields)
    df["forecast_datetime"] = pd.to_datetime(df.pop("time"), utc=True)
    return df


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
    all_rows, failed = [], []
    for spot in spots:
        spot_id, lat, lon = spot["spot_id"], spot["localisation_lat"], spot["localisation_lon"]
        try:
            marine = fetch_hourly(config.MARINE_API_URL, lat, lon, MARINE_FIELDS)
            weather = fetch_hourly(config.WEATHER_API_URL, lat, lon, WEATHER_FIELDS, {"wind_speed_unit": "kmh"})
            rows = build_rows(spot_id, marine, weather, retrieved_at)
            if not args.dry_run:
                db.upsert(client, "marine_forecast", rows, on_conflict="spot_id,forecast_datetime")
            all_rows += rows
            no_tide = sum(r["tide_stage"] is None for r in rows)
            print(f"{spot_id} : {len(rows)} heures ({no_tide} sans marée)")
        except Exception as exc:  # un spot en erreur n'arrête pas les autres
            failed.append(spot_id)
            print(f"{spot_id} : ERREUR {exc}", file=sys.stderr)

    if args.dry_run and all_rows:
        pd.DataFrame(all_rows).to_csv("forecast_preview.csv", index=False)
        print("Aperçu enregistré dans forecast_preview.csv (rien n'a été écrit en base).")

    if failed:
        # code de sortie 1 : GitHub Actions ne lancera pas le scoring
        sys.exit(f"Collecte en échec pour : {', '.join(failed)}")


if __name__ == "__main__":
    main()
