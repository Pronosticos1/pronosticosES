"""
Validación independiente de viento para EM Central Izalco.
No modifica el archivo operativo data/wind_forecast_latest.csv.
Modelo: DWD ICON Seamless
"""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import openmeteo_requests
import requests_cache
from retry_requests import retry

LAT = 13.72133331874404
LON = -89.71074386732839
TIMEZONE = "America/El_Salvador"

MODEL_LABEL = "DWD ICON Seamless"
MODEL = "icon_seamless"
CELL_SELECTION = "nearest"

BASE_OUTPUT_DIR = os.path.join("data", "validation", "icon")
LATEST_FILE = os.path.join(BASE_OUTPUT_DIR, "wind_forecast_latest.csv")
os.makedirs(BASE_OUTPUT_DIR, exist_ok=True)

def grados_a_punto_cardinal_simple(grados):
    if pd.isna(grados):
        return "Sin datos"
    grados = float(grados) % 360
    puntos = [
        (0.0, 22.5, "Norte"),
        (22.5, 67.5, "Noreste"),
        (67.5, 112.5, "Este"),
        (112.5, 157.5, "Sureste"),
        (157.5, 202.5, "Sur"),
        (202.5, 247.5, "Suroeste"),
        (247.5, 292.5, "Oeste"),
        (292.5, 337.5, "Noroeste"),
        (337.5, 360.0, "Norte"),
    ]
    for inicio, fin, nombre in puntos:
        if inicio <= grados < fin:
            return nombre
    return "Norte"

def grados_a_punto_cardinal_detalle(grados):
    if pd.isna(grados):
        return "Sin datos"
    grados = float(grados) % 360
    nombres = [
        "Norte", "Nornoreste", "Noreste", "Estenoreste",
        "Este", "Estesureste", "Sureste", "Sursureste",
        "Sur", "Sursuroeste", "Suroeste", "Oestesuroeste",
        "Oeste", "Oestenoroeste", "Noroeste", "Nornoroeste",
    ]
    indice = int((grados + 11.25) // 22.5) % 16
    return nombres[indice]

def hacia_donde_va(grados):
    if pd.isna(grados):
        return "Sin datos"
    return grados_a_punto_cardinal_simple((float(grados) + 180.0) % 360.0)

cache_session = requests_cache.CachedSession(".cache_validation_icon", expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

HOURLY_VARS = [
    "wind_speed_10m",
    "wind_speed_100m",
    "wind_direction_10m",
    "wind_direction_100m",
]

params = {
    "latitude": LAT,
    "longitude": LON,
    "hourly": HOURLY_VARS,
    "models": MODEL,
    "forecast_days": 3,
    "timezone": TIMEZONE,
    "wind_speed_unit": "kmh",
    "cell_selection": CELL_SELECTION,
}

print(f"Modelo de validación: {MODEL_LABEL}")
print(f"Coordenada solicitada: {LAT:.6f}, {LON:.6f}")
print(f"Selección de celda: {CELL_SELECTION}")

responses = openmeteo.weather_api(
    "https://api.open-meteo.com/v1/forecast",
    params=params,
)
response = responses[0]

print(f"Celda utilizada: {response.Latitude():.6f}, {response.Longitude():.6f}")
print(f"Elevación de la celda: {response.Elevation():.1f} m")

hourly = response.Hourly()
vals = [hourly.Variables(i).ValuesAsNumpy() for i in range(len(HOURLY_VARS))]

date_index = pd.date_range(
    start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
    end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
    freq=pd.Timedelta(seconds=hourly.Interval()),
    inclusive="left",
).tz_convert(TIMEZONE)

data = {"fecha_hora": date_index}
for name, arr in zip(HOURLY_VARS, vals):
    data[name] = arr

df = pd.DataFrame(data)
df["fecha"] = df["fecha_hora"].dt.date.astype(str)
df["hora"] = df["fecha_hora"].dt.hour
df["dia_semana"] = df["fecha_hora"].dt.day_name()

df["viene_de_10m"] = df["wind_direction_10m"].apply(grados_a_punto_cardinal_simple)
df["viene_de_100m"] = df["wind_direction_100m"].apply(grados_a_punto_cardinal_simple)
df["viene_de_10m_detalle"] = df["wind_direction_10m"].apply(grados_a_punto_cardinal_detalle)
df["viene_de_100m_detalle"] = df["wind_direction_100m"].apply(grados_a_punto_cardinal_detalle)
df["va_hacia_10m"] = df["wind_direction_10m"].apply(hacia_donde_va)
df["va_hacia_100m"] = df["wind_direction_100m"].apply(hacia_donde_va)

df["fecha_hora"] = df["fecha_hora"].dt.tz_localize(None)

df.to_csv(LATEST_FILE, index=False, encoding="utf-8")

fecha = datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()
history_dir = os.path.join(BASE_OUTPUT_DIR, fecha)
os.makedirs(history_dir, exist_ok=True)
history_file = os.path.join(history_dir, f"wind_forecast_{fecha}.csv")
df.to_csv(history_file, index=False, encoding="utf-8")

print(f"CSV actualizado: {LATEST_FILE}")
print(f"Histórico diario: {history_file}")
print(f"Filas: {len(df)}")
