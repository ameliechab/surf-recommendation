"""Paramètres communs, lus depuis le fichier .env (ou les secrets GitHub)."""
import os

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "")

# Google Sheet "Matrice de passage" : l'ID est dans l'URL, entre /d/ et /edit.
# Chaque onglet a son gid, visible à la fin de l'URL quand on clique dessus (#gid=...).
SHEET_ID = os.getenv("SHEET_ID", "1i_PB1GW9v_wIHYUn5sd08mzb2EUtB7GXq3hLMeN8o1I")
SHEET_GIDS = {
    "surf_spot_properties": os.getenv("GID_SPOT_PROPERTIES", ""),
    "surf_spot_conditions_reference": os.getenv("GID_SPOT_CONDITIONS", ""),
    "surf_level_conditions_reference": os.getenv("GID_LEVEL_CONDITIONS", ""),
}

# Open-Meteo (gratuit, sans clé pour un usage non commercial)
MARINE_API_URL = "https://marine-api.open-meteo.com/v1/marine"
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
PAST_DAYS = 1       # nécessaire au calcul de la marée des premières heures
FORECAST_DAYS = 8   # idem pour les dernières heures
DATA_SOURCE = "Open-Meteo Marine + Open-Meteo Weather"
