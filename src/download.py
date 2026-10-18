"""Descarga de series desde SIE (Banxico), INEGI y FRED.

Regla del proyecto: la respuesta de cada API se guarda TAL COMO LLEGA en
data/raw/, con la fecha de consulta en el nombre. Nunca se edita a mano;
toda limpieza ocurre después, con código (Semana 2).

Uso, desde la raíz del repositorio y con el .venv activo:
    python -m src.download
"""
import json
import os
import time
from datetime import date, datetime

import requests
from dotenv import load_dotenv

from src import config

load_dotenv(config.ROOT / ".env")

RETRY_STATUS = {429, 500, 502, 503, 504}  # saturación o fallas temporales del servidor


# ----------------------------------------------------------------------------
# Utilidades generales
# ----------------------------------------------------------------------------
def get_token(name: str) -> str:
    """Lee un token del .env y falla con un mensaje claro si falta."""
    token = os.getenv(name)
    if not token or token.startswith("pon_aqui"):
        raise RuntimeError(f"Falta {name} en el archivo .env")
    return token


def redact(message: str) -> str:
    """Oculta los tokens en mensajes de error (la URL de INEGI incluye el token)."""
    for name in ("BANXICO_TOKEN", "INEGI_TOKEN"):
        value = os.getenv(name)
        if value:
            message = message.replace(value, "***")
    return message


def get_with_retry(session, url, headers=None, params=None, retries=3, backoff=5):
    """GET con reintentos ante errores temporales (espera 5 s, 10 s, ...)."""
    for attempt in range(1, retries + 1):
        response = session.get(url, headers=headers, params=params, timeout=60)
        if response.status_code in RETRY_STATUS and attempt < retries:
            time.sleep(backoff * attempt)
            continue
        response.raise_for_status()  # cualquier otro error (401, 404...) detiene el proceso
        return response


def save_raw(text: str, source: str, series_id: str, ext: str):
    """Guarda la respuesta cruda: data/raw/<fuente>_<id>_<fecha>.<ext>."""
    config.DATA_RAW.mkdir(parents=True, exist_ok=True)
    path = config.DATA_RAW / f"{source.lower()}_{series_id}_{date.today().isoformat()}.{ext}"
    path.write_text(text, encoding="utf-8")
    return path


# ----------------------------------------------------------------------------
# SIE de Banxico
# ----------------------------------------------------------------------------
def sie_headers() -> dict:
    return {"Bmx-Token": get_token("BANXICO_TOKEN"), "Accept": "application/json"}


def sie_metadata(series_id: str, session) -> dict:
    """Metadatos de una serie: título, periodicidad, unidad, fechas de inicio y fin."""
    url = f"{config.SIE_BASE}/series/{series_id}"
    response = get_with_retry(session, url, headers=sie_headers())
    return response.json()["bmx"]["series"][0]


def sie_data(series_id: str, session, start=config.START_DATE, end=None):
    """Datos de una serie en un rango de fechas (aaaa-mm-dd)."""
    end = end or date.today().isoformat()
    url = f"{config.SIE_BASE}/series/{series_id}/datos/{start}/{end}"
    return get_with_retry(session, url, headers=sie_headers())


def count_sie(text: str) -> int:
    series = json.loads(text)["bmx"]["series"][0]
    return len(series.get("datos") or [])


# ----------------------------------------------------------------------------
# INEGI
# ----------------------------------------------------------------------------
def inegi_url(method: str, indicator_id: str, recent: bool = False) -> str:
    """Construye la URL de INEGI. El token va dentro de la ruta: nunca imprimas esta URL."""
    token = get_token("INEGI_TOKEN")
    if method == "INDICATOR":
        return (f"{config.INEGI_BASE}/INDICATOR/{indicator_id}/es/{config.INEGI_GEO}/"
                f"{str(recent).lower()}/{config.INEGI_SOURCE}/2.0/{token}")
    if method == "CL_INDICATOR":
        return f"{config.INEGI_BASE}/CL_INDICATOR/{indicator_id}/es/{config.INEGI_SOURCE}/2.0/{token}"
    raise ValueError(method)


def inegi_data(indicator_id: str, session, recent: bool = False):
    return get_with_retry(session, inegi_url("INDICATOR", indicator_id, recent), params={"type": "json"})


def inegi_name(indicator_id: str, session) -> str:
    response = get_with_retry(session, inegi_url("CL_INDICATOR", indicator_id), params={"type": "json"})
    return response.json()["CODE"][0]["Description"]


def count_inegi(text: str) -> int:
    return len(json.loads(text)["Series"][0]["OBSERVATIONS"])


# ----------------------------------------------------------------------------
# FRED
# ----------------------------------------------------------------------------
def fred_data(series_id: str, session, start=config.START_DATE):
    return get_with_retry(session, config.FRED_CSV, params={"id": series_id, "cosd": start})


def count_fred(text: str) -> int:
    return max(len(text.strip().splitlines()) - 1, 0)  # menos la fila de encabezado


# ----------------------------------------------------------------------------
# Orquestación
# ----------------------------------------------------------------------------
def download_series(spec: dict, session):
    """Descarga una serie del catálogo y devuelve su registro para el manifiesto."""
    source, series_id = spec["source"], spec["id"]
    if source == "SIE":
        response, ext, counter = sie_data(series_id, session), "json", count_sie
    elif source == "INEGI":
        response, ext, counter = inegi_data(series_id, session), "json", count_inegi
    elif source == "FRED":
        response, ext, counter = fred_data(series_id, session), "csv", count_fred
    else:
        raise ValueError(f"Fuente desconocida: {source}")

    path = save_raw(response.text, source, series_id, ext)
    return {
        "key": spec["key"],
        "source": source,
        "id": series_id,
        "file": path.name,
        "n_obs": counter(response.text),
        "downloaded_at": datetime.now().isoformat(timespec="seconds"),
    }


def download_all(session=None) -> list:
    session = session or requests.Session()
    manifest = []
    for spec in config.SERIES:
        if not spec["id"]:
            print(f"[OMITIDA] {spec['key']}: falta el ID en config.py")
            continue
        try:
            record = download_series(spec, session)
            manifest.append(record)
            print(f"[OK] {record['key']:<14} {record['n_obs']:>6} obs -> {record['file']}")
        except Exception as exc:  # una serie fallida no detiene las demás
            print(f"[ERROR] {spec['key']}: {type(exc).__name__}: {redact(str(exc))}")
        time.sleep(0.5)  # cortesía con los límites de las APIs

    manifest_path = config.DATA_RAW / f"manifest_{date.today().isoformat()}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Manifiesto: {manifest_path.name}")
    return manifest


if __name__ == "__main__":
    download_all()
