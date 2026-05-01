import numpy as np
import pandas as pd
import openmeteo_requests
import requests_cache
from retry_requests import retry

# Coordenadas del polígono Laguna, El Salvador
# Ajusta lat/lon al centroide real de tu polígono
LAT = 13.50
LON = -89.20

# Setup cliente Open-Meteo con caché y reintentos
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
openmeteo = openmeteo_requests.Client(session=retry_session)

hourly_vars = [
    "wind_speed_10m",
    "wind_speed_100m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "wind_direction_100m"
]

params = {
    "latitude": LAT,
    "longitude": LON,
    "hourly": hourly_vars,
    "models": "ecmwf_ifs",
    "forecast_days": 3,
    "timezone": "America/El_Salvador",
    "windspeed_unit": "kmh"
}

url = "https://api.open-meteo.com/v1/forecast"
responses = openmeteo.weather_api(url, params=params)
response = responses[0]
hourly = response.Hourly()

vals = [hourly.Variables(i).ValuesAsNumpy() for i in range(len(hourly_vars))]

date_index = pd.date_range(
    start=pd.to_datetime(hourly.Time(), unit="s", utc=True).tz_convert("America/El_Salvador"),
    end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True).tz_convert("America/El_Salvador"),
    freq=pd.Timedelta(seconds=hourly.Interval()),
    inclusive="left"
)

df = pd.DataFrame({
    "fecha_hora": date_index,
    "velocidad_10m_kmh": vals[0],
    "velocidad_100m_kmh": vals[1],
    "rafagas_10m_kmh": vals[2],
    "direccion_10m_deg": vals[3],
    "direccion_100m_deg": vals[4]
})

# Columna de condición favorable para quemas
# Favorable: dirección entre 90° y 270° (viento hacia el norte)
df["condicion_10m"] = df["direccion_10m_deg"].apply(
    lambda x: "Favorable" if 90 <= x <= 270 else "No favorable"
)
df["condicion_100m"] = df["direccion_100m_deg"].apply(
    lambda x: "Favorable" if 90 <= x <= 270 else "No favorable"
)

# Quitar timezone para compatibilidad con Power BI
df["fecha_hora"] = df["fecha_hora"].dt.tz_localize(None)