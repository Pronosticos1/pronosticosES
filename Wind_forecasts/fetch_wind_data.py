"""
fetch_wind_data.py
==================
Descarga pronóstico de viento (3 días) para EM Central Izalco, El Salvador,
y guarda un CSV listo para Apps Script / Power BI.

Variables: velocidad y dirección a 10 m y 100 m
Modelo: ECMWF IFS vía Open-Meteo API
Punto de validación: EM Central Izalco

Output: data/wind_forecast_latest.csv
"""

import os
import pandas as pd
import openmeteo_requests
import requests_cache
from retry_requests import retry

# ─────────────────────────────────────────────
# UBICACIÓN: EM CENTRAL IZALCO
# ─────────────────────────────────────────────
LAT = 13.72133331874404
LON = -89.71074386732839

# Si en el futuro quieres usar exactamente la Laguna Facultativa:
# LAT = 13.71783836415580
# LON = -89.71062466044499

TIMEZONE = "America/El_Salvador"

# ─────────────────────────────────────────────
# SALIDA
# ─────────────────────────────────────────────
OUTPUT_DIR = "data"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "wind_forecast_latest.csv")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# FUNCIONES DE DIRECCIÓN
# ─────────────────────────────────────────────
def grados_a_punto_cardinal_simple(grados):
    """8 puntos cardinales: N, NE, E, SE, S, SO, O, NO."""
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
    """16 puntos cardinales detallados."""
    if pd.isna(grados):
        return "Sin datos"

    grados = float(grados) % 360

    puntos = [
        (0.00, 11.25, "Norte"),
        (11.25, 33.75, "Nornoreste"),
        (33.75, 56.25, "Noreste"),
        (56.25, 78.75, "Estenoreste"),
        (78.75, 101.25, "Este"),
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
        (326.25, 348.75, "Nornoroeste"),
        (348.75, 360.00, "Norte"),
    ]

    for inicio, fin, nombre in puntos:
        if inicio <= grados < fin:
            return nombre

    return "Norte"


def hacia_donde_va(grados):
    """Hacia dónde se desplaza el viento: 180° opuesto a su procedencia."""
    if pd.isna(grados):
        return "Sin datos"

    return grados_a_punto_cardinal_simple((float(grados) + 180.0) % 360.0)


# ─────────────────────────────────────────────
# CLIENTE OPEN-METEO
# ─────────────────────────────────────────────
cache_session = requests_cache.CachedSession(
    ".cache",
    expire_after=3600
)

retry_session = retry(
    cache_session,
    retries=5,
    backoff_factor=0.2
)

openmeteo = openmeteo_requests.Client(
    session=retry_session
)

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
    "models": "ecmwf_ifs",
    "forecast_days": 3,
    "timezone": TIMEZONE,
    "wind_speed_unit": "kmh",
    "cell_selection": "nearest",
}

# ─────────────────────────────────────────────
# DESCARGAR PRONÓSTICO
# ─────────────────────────────────────────────
print("Descargando pronóstico para EM Central Izalco...")
print(f"Coordenada solicitada: {LAT:.6f}, {LON:.6f}")

responses = openmeteo.weather_api(
    "https://api.open-meteo.com/v1/forecast",
    params=params
)

response = responses[0]

print(
    f"Celda utilizada por Open-Meteo: "
    f"{response.Latitude():.6f}, {response.Longitude():.6f}"
)
print(f"Elevación de la celda: {response.Elevation():.1f} m")
print(f"Zona horaria: {response.Timezone()}")

hourly = response.Hourly()

# El orden debe coincidir exactamente con HOURLY_VARS.
vals = [
    hourly.Variables(i).ValuesAsNumpy()
    for i in range(len(HOURLY_VARS))
]

# Open-Meteo devuelve timestamps que convertimos a hora local de El Salvador.
date_index = pd.date_range(
    start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
    end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
    freq=pd.Timedelta(seconds=hourly.Interval()),
    inclusive="left",
).tz_convert(TIMEZONE)

data = {
    "fecha_hora": date_index
}

for name, arr in zip(HOURLY_VARS, vals):
    data[name] = arr

df = pd.DataFrame(data)

# ─────────────────────────────────────────────
# COLUMNAS EXTRA
# ─────────────────────────────────────────────
df["fecha"] = df["fecha_hora"].dt.date.astype(str)
df["hora"] = df["fecha_hora"].dt.hour
df["dia_semana"] = df["fecha_hora"].dt.day_name()

# De dónde VIENE el viento
df["viene_de_10m"] = df["wind_direction_10m"].apply(
    grados_a_punto_cardinal_simple
)
df["viene_de_100m"] = df["wind_direction_100m"].apply(
    grados_a_punto_cardinal_simple
)

# Dirección detallada
df["viene_de_10m_detalle"] = df["wind_direction_10m"].apply(
    grados_a_punto_cardinal_detalle
)
df["viene_de_100m_detalle"] = df["wind_direction_100m"].apply(
    grados_a_punto_cardinal_detalle
)

# Hacia dónde VA el viento
df["va_hacia_10m"] = df["wind_direction_10m"].apply(
    hacia_donde_va
)
df["va_hacia_100m"] = df["wind_direction_100m"].apply(
    hacia_donde_va
)

# Quitar timezone para mantener compatibilidad con el CSV actual
df["fecha_hora"] = df["fecha_hora"].dt.tz_localize(None)

# ─────────────────────────────────────────────
# GUARDAR CSV
# ─────────────────────────────────────────────
df.to_csv(
    OUTPUT_FILE,
    index=False,
    encoding="utf-8"
)

print(f"\n✅ CSV guardado en: {OUTPUT_FILE}")
print(f"   Filas: {len(df)}")
print(f"   Columnas: {list(df.columns)}")
print(
    f"   Período: "
    f"{df['fecha_hora'].min()} → {df['fecha_hora'].max()}"
)

print("\nPrimeras filas:")
print(
    df[
        [
            "fecha_hora",
            "wind_speed_10m",
            "wind_direction_10m",
            "viene_de_10m",
            "va_hacia_10m",
        ]
    ].head(8).to_string(index=False)
)
