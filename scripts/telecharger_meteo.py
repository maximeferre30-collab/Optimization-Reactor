"""Télécharge les séries météo horaires des sites N4 (archive Open-Meteo, ERA5).

Usage :
    python scripts/telecharger_meteo.py
Écrit data/meteo_<site>.csv (température sèche, humidité relative, pression).
Les fichiers sont versionnés : l'étude est reproductible sans réseau.

Source : https://open-meteo.com/en/docs/historical-weather-api
(réanalyse ERA5 / ERA5-Land de Copernicus, licence CC BY 4.0).
"""

import json
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parents[1] / "data"
SITES = {
    "chooz": (50.090, 4.789),   # Chooz B (Ardennes), 2 tranches N4
    "civaux": (46.456, 0.653),  # Civaux (Vienne), 2 tranches N4
}
DEBUT, FIN = "2015-01-01", "2024-12-31"


def telecharger(site: str, lat: float, lon: float) -> pd.DataFrame:
    params = {
        "latitude": lat, "longitude": lon, "start_date": DEBUT, "end_date": FIN,
        "hourly": "temperature_2m,relative_humidity_2m,surface_pressure",
        "timezone": "UTC",
    }
    url = "https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(params)
    with urllib.request.urlopen(url, timeout=120) as rep:
        d = json.load(rep)["hourly"]
    df = pd.DataFrame({
        "temps_utc": pd.to_datetime(d["time"]),
        "T_seche_C": pd.to_numeric(d["temperature_2m"]),
        "HR_pourcent": pd.to_numeric(d["relative_humidity_2m"]),
        "P_hPa": pd.to_numeric(d["surface_pressure"]),
    })
    return df


def main() -> None:
    DATA.mkdir(exist_ok=True)
    for site, (lat, lon) in SITES.items():
        df = telecharger(site, lat, lon)
        manquants = int(df.isna().any(axis=1).sum())
        df.to_csv(DATA / f"meteo_{site}.csv", index=False, float_format="%.2f")
        print(f"{site} : {len(df)} heures, {manquants} incomplètes, "
              f"T moy {df['T_seche_C'].mean():.1f} °C, HR moy {df['HR_pourcent'].mean():.0f} %")


if __name__ == "__main__":
    main()
