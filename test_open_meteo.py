import requests
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

#1 FONCTION CALCUL MAREE
def calculate_tide_stage(df):
    """
    Détermine le stade de marée à partir de l'évolution
    du niveau de la mer.

    Stades possibles :
    - basse
    - montante
    - mi-maree
    - pleine
    - descendante
    """

    df = df.copy()

    # ---------------------------------------------------------
    # 1. Préparation des données
    # ---------------------------------------------------------

    df = df.sort_values("forecast_datetime").reset_index(drop=True)

    df["sea_level_height_m"] = pd.to_numeric(
        df["sea_level_height_m"],
        errors="coerce"
    )

    df["tide_stage"] = None

    # ---------------------------------------------------------
    # 2. Détection des marées basses et hautes
    # ---------------------------------------------------------

    extrema = []

    for i in range(1, len(df) - 1):

        previous_level = df.loc[i - 1, "sea_level_height_m"]
        current_level = df.loc[i, "sea_level_height_m"]
        next_level = df.loc[i + 1, "sea_level_height_m"]

        # Une des valeurs est manquante
        if pd.isna(previous_level) or pd.isna(current_level) or pd.isna(next_level):
            continue

        # Marée basse : niveau inférieur aux deux heures voisines
        if current_level <= previous_level and current_level <= next_level:
            extrema.append((i, "basse"))

        # Marée haute : niveau supérieur aux deux heures voisines
        elif current_level >= previous_level and current_level >= next_level:
            extrema.append((i, "pleine"))

    # ---------------------------------------------------------
    # 3. Attribution des stades entre les extrêmes
    # ---------------------------------------------------------

    for j in range(len(extrema) - 1):

        start_index, start_type = extrema[j]
        end_index, end_type = extrema[j + 1]

        start_level = df.loc[start_index, "sea_level_height_m"]
        end_level = df.loc[end_index, "sea_level_height_m"]

        amplitude = abs(end_level - start_level)

        # Évite une division par zéro
        if amplitude == 0:
            continue

        # Cas 1 : marée montante
        if start_type == "basse" and end_type == "pleine":

            for i in range(start_index, end_index + 1):

                current_level = df.loc[i, "sea_level_height_m"]

                if pd.isna(current_level):
                    continue

                progression = (
                    current_level - start_level
                ) / (end_level - start_level)

                if progression <= 0.05:
                    stage = "basse"

                elif progression < 0.25:
                    stage = "montante"

                elif progression < 0.75:
                    stage = "mi-maree"

                elif progression < 0.95:
                    stage = "montante"

                else:
                    stage = "pleine"

                df.loc[i, "tide_stage"] = stage

        # Cas 2 : marée descendante
        elif start_type == "pleine" and end_type == "basse":

            for i in range(start_index, end_index + 1):

                current_level = df.loc[i, "sea_level_height_m"]

                if pd.isna(current_level):
                    continue

                progression = (
                    start_level - current_level
                ) / (start_level - end_level)

                if progression <= 0.05:
                    stage = "pleine"

                elif progression < 0.25:
                    stage = "descendante"

                elif progression < 0.75:
                    stage = "mi-maree"

                elif progression < 0.95:
                    stage = "descendante"

                else:
                    stage = "basse"

                df.loc[i, "tide_stage"] = stage

    # ---------------------------------------------------------
    # 4. Suppression de la colonne temporaire éventuelle
    # ---------------------------------------------------------

    return df

#2 RECUPERATION INFOS MER & METEO

# =========================
# SPOT
# =========================

spot_id = "la_torche"

latitude = 47.8432
longitude = -4.3476



# =========================
# OPEN-METEO MARINE
# =========================

marine_url = "https://marine-api.open-meteo.com/v1/marine"

marine_params = {
    "latitude": latitude,
    "longitude": longitude,

    "hourly": [
        "swell_wave_height",
        "swell_wave_period",
        "swell_wave_direction",
        "sea_surface_temperature",
        "sea_level_height_msl"
    ],

    "forecast_days": 7,
    "timezone": "UTC"
}

marine_response = requests.get(
    marine_url,
    params=marine_params
)

marine_response.raise_for_status()

marine_data = marine_response.json()


# =========================
# OPEN-METEO WEATHER
# =========================

weather_url = "https://api.open-meteo.com/v1/forecast"

weather_params = {
    "latitude": latitude,
    "longitude": longitude,

    "hourly": [
        "temperature_2m",
        "wind_speed_10m",
        "wind_direction_10m",
        "precipitation",
        "uv_index"
    ],

    "forecast_days": 7,
    "timezone": "UTC"
}

weather_response = requests.get(
    weather_url,
    params=weather_params
)

weather_response.raise_for_status()

weather_data = weather_response.json()


# =========================
# DATAFRAMES
# =========================

marine_df = pd.DataFrame(marine_data["hourly"])

weather_df = pd.DataFrame(weather_data["hourly"])


# =========================
# RENOMMAGE DES COLONNES
# =========================

marine_df = marine_df.rename(columns={
    "time": "forecast_datetime",
    "swell_wave_height": "swell_height_m",
    "swell_wave_period": "swell_period_s",
    "swell_wave_direction": "swell_direction_deg",
    "sea_surface_temperature": "water_temp_c",
    "sea_level_height_msl": "sea_level_height_m"
})

weather_df = weather_df.rename(columns={
    "time": "forecast_datetime",
    "temperature_2m": "air_temp_c",
    "wind_speed_10m": "wind_speed_kmh",
    "wind_direction_10m": "wind_direction_deg",
    "precipitation": "precipitation_mm"
})


# =========================
# FUSION MARINE + WEATHER
# =========================

df = marine_df.merge(
    weather_df,
    on="forecast_datetime",
    how="left"
)

# =========================
# Calcul du stade de marée
# =========================

df = calculate_tide_stage(df)


# =========================
# INFORMATIONS DE RECUPERATION
# =========================

df["spot_id"] = spot_id

df["latitude"] = latitude
df["longitude"] = longitude

df["retrieved_at"] = datetime.now(timezone.utc)

df["data_source"] = "open-meteo"

# =========================
# ORDRE DES COLONNES
# =========================

df = df[
    [
        "spot_id",
        "latitude",
        "longitude",
        "forecast_datetime",
        "retrieved_at",

        "swell_height_m",
        "swell_period_s",
        "swell_direction_deg",

        "wind_speed_kmh",
        "wind_direction_deg",

        "air_temp_c",
        "water_temp_c",

        "uv_index",
        "precipitation_mm",

        "sea_level_height_m",
        "tide_stage",

        "data_source"
    ]
]


# ============================================================
# 9. AFFICHAGE
# ============================================================

#print("\n===== 10 PREMIERES LIGNES =====\n")

#print(
#    df.head(10).to_string(index=False)
#)


print(
    df[
        [
            "forecast_datetime",
            "sea_level_height_m",
            "tide_stage"
        ]
    ].head(30).to_string(index=False)
)


# ============================================================
# 10. SAUVEGARDE CSV
# ============================================================

# output_dir = Path("data/raw")

#output_dir.mkdir(
#    parents=True,
#    exist_ok=True
#)

#output_file = output_dir / f"{spot_id}_forecast.csv"

#df.to_csv(
#    output_file,
#    index=False
#)

#print(f"\n===== FICHIER SAUVEGARDE =====")

#print(output_file)