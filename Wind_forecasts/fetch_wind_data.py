"""
fetch_wind_data.py
==================
Descarga pronóstico de viento (3 días) para el área de Laguna, El Salvador
y guarda un CSV listo para Power BI.

Variables: velocidad y dirección a 10m y 100m
Modelo: ECMWF IFS vía Open-Meteo API (gratuito)
Zona: centroide + radio 10 km → malla de puntos → promedio areal

Ejecutar: python fetch_wind_data.py
Output:   data/wind_forecast_latest.csv
"""

import os
import numpy as np
import pandas as pd
import openmeteo_requests
import requests_cache
from retry_requests import retry

# ─────────────────────────────────────────────
# CONFIGURACIÓN DEL ÁREA (centroide + radio)
# ─────────────────────────────────────────────
CENTROID_LAT = 13.50
CENTROID_LON = -89.20
RADIO_KM     = 10.0
GRID_STEP_KM = 4.0

RAD_DEG  = RADIO_KM  / 111.0
STEP_DEG = GRID_STEP_KM / 111.0

# ─────────────────────────────────────────────
# SALIDA
# ─────────────────────────────────────────────
OUTPUT_DIR  = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "wind_forecast_latest.csv")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# CONSTRUIR MALLA DE PUNTOS DENTRO DEL CÍRCULO
# ─────────────────────────────────────────────
lats = np.arange(CENTROID_LAT - RAD_DEG, CENTROID_LAT + RAD_DEG + STEP_DEG, STEP_DEG)
lons = np.arange(CENTROID_LON - RAD_DEG, CENTROID_LON + RAD_DEG + STEP_DEG, STEP_DEG)

points = []
for lat in lats:
    for lon in lons:
        dist = np.sqrt(((lat - CENTROID_LAT) * 111) ** 2 + ((lon - CENTROID_LON) * 111) ** 2)
        if dist <= RADIO_KM:
            points.append((lat, lon))

print(f"Puntos de muestreo dentro del área: {len(points)}")

# ─────────────────────────────────────────────
# FUNCIONES DE DIRECCIÓN
# ─────────────────────────────────────────────
def grados_a_punto_cardinal_simple(grados):
    """8 puntos cardinales: N, NE, E, SE, S, SO, O, NO"""
    if pd.isna(grados):
        return "Sin datos"
    grados = grados % 360
    puntos = [
        (  0.0,  22.5, "Norte"),
        ( 22.5,  67.5, "Noreste"),
        ( 67.5, 112.5, "Este"),
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
    """16 puntos cardinales detallados"""
    if pd.isna(grados):
        return "Sin datos"
    grados = grados % 360
    puntos = [
        (  0.00,  11.25, "Norte"),
        ( 11.25,  33.75, "Nornoreste"),
        ( 33.75,  56.25, "Noreste"),
        ( 56.25,  78.75, "Estenoreste"),
        ( 78.75, 101.25, "Este"),
        (101.25, 123.75, "Estesureste"),
        (123.75, 146.25, "Sureste"),
        (146.25, 168.75, "Sursureste"),
        (168.75, 191.25, "Sur"),
        (191.25, 213.75, "Sursuroeste"),
        (213.75, 236.25, "Suroeste"),
        (236.25, 258.75, "Oestesuroeste"),
        (258.75, 281.25, "Oeste"),
        (281.25, 303.75, "Oestenoroeste"),
        (303.75, 326.25, "Noroeste"),
        (326.25, 348.75, "Nornoreste"),
        (348.75, 360.00, "Norte"),
    ]
    for inicio, fin, nombre in puntos:
        if inicio <= grados < fin:
            return nombre
    return "Norte"

def hacia_donde_va(grados):
    """Hacia dónde SE DESPLAZA el viento (opuesto a de dónde viene)"""
    if pd.isna(grados):
        return "Sin datos"
    return grados_a_punto_cardinal_simple((grados + 180) % 360)

# ─────────────────────────────────────────────
# CLIENTE OPEN-METEO
# ─────────────────────────────────────────────
cache_session  = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session  = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo      = openmeteo_requests.Client(session=retry_session)

HOURLY_VARS = [
    "wind_speed_10m",
    "wind_speed_100m",
    "wind_direction_10m",
    "wind_direction_100m",
]

# ─────────────────────────────────────────────
# DESCARGAR DATOS PARA CADA PUNTO
# ─────────────────────────────────────────────
all_dfs = []

for i, (lat, lon) in enumerate(points):
    print(f"  Descargando punto {i+1}/{len(points)}: lat={lat:.3f}, lon={lon:.3f}")

    params = {
        "latitude":       lat,
        "longitude":      lon,
        "hourly":         HOURLY_VARS,
        "models":         "ecmwf_ifs",
        "forecast_days":  3,
        "timezone":       "America/El_Salvador",
        "windspeed_unit": "kmh",
    }

    try:
        responses = openmeteo.weather_api("https://api.open-meteo.com/v1/forecast", params=params)
        response  = responses[0]
        hourly    = response.Hourly()

        vals = [hourly.Variables(j).ValuesAsNumpy() for j in range(len(HOURLY_VARS))]

        date_index = pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True).tz_convert("America/El_Salvador"),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True).tz_convert("America/El_Salvador"),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left",
        )

        data = {"fecha_hora": date_index, "lat": lat, "lon": lon}
        for name, arr in zip(HOURLY_VARS, vals):
            data[name] = arr

        all_dfs.append(pd.DataFrame(data))

    except Exception as e:
        print(f"    ⚠️  Error en punto ({lat}, {lon}): {e}")
        continue

# ─────────────────────────────────────────────
# PROMEDIO AREAL POR HORA
# ─────────────────────────────────────────────
df_all  = pd.concat(all_dfs, ignore_index=True)
df_mean = (
    df_all
    .groupby("fecha_hora")[HOURLY_VARS]
    .mean()
    .reset_index()
)

# ─────────────────────────────────────────────
# COLUMNAS EXTRA PARA POWER BI
# ─────────────────────────────────────────────
df_mean["fecha"]      = df_mean["fecha_hora"].dt.date.astype(str)
df_mean["hora"]       = df_mean["fecha_hora"].dt.hour
df_mean["dia_semana"] = df_mean["fecha_hora"].dt.day_name()

# ── Condición de quema ──────────────────────────────────────────
df_mean["condicion_10m"]  = df_mean["wind_direction_10m"].apply(
    lambda x: "Favorable" if 90 <= x <= 270 else "No favorable"
)
df_mean["condicion_100m"] = df_mean["wind_direction_100m"].apply(
    lambda x: "Favorable" if 90 <= x <= 270 else "No favorable"
)

# ── De dónde VIENE el viento (8 puntos) ─────────────────────────
df_mean["viene_de_10m"]  = df_mean["wind_direction_10m"].apply(grados_a_punto_cardinal_simple)
df_mean["viene_de_100m"] = df_mean["wind_direction_100m"].apply(grados_a_punto_cardinal_simple)

# ── De dónde VIENE el viento (16 puntos, más detalle) ───────────
df_mean["viene_de_10m_detalle"]  = df_mean["wind_direction_10m"].apply(grados_a_punto_cardinal_detalle)
df_mean["viene_de_100m_detalle"] = df_mean["wind_direction_100m"].apply(grados_a_punto_cardinal_detalle)

# ── Hacia dónde VA el viento (8 puntos) ─────────────────────────
df_mean["va_hacia_10m"]  = df_mean["wind_direction_10m"].apply(hacia_donde_va)
df_mean["va_hacia_100m"] = df_mean["wind_direction_100m"].apply(hacia_donde_va)

# ── Quitar timezone para Power BI ───────────────────────────────
df_mean["fecha_hora"] = df_mean["fecha_hora"].dt.tz_localize(None)

# ─────────────────────────────────────────────
# GUARDAR CSV
# ─────────────────────────────────────────────
df_mean.to_csv(OUTPUT_FILE, index=False, encoding="utf-8")

print(f"\n✅ CSV guardado en: {OUTPUT_FILE}")
print(f"   Filas: {len(df_mean)}  |  Columnas: {list(df_mean.columns)}")
print(f"   Período: {df_mean['fecha_hora'].min()} → {df_mean['fecha_hora'].max()}")
