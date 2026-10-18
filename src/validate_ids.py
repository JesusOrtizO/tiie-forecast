"""Valida que cada ID del catálogo corresponda a la serie esperada
y genera el diccionario de datos en reports/diccionario_datos.csv.

Uso, desde la raíz del repositorio y con el .venv activo:
    python -m src.validate_ids
"""
import csv
import sys
import unicodedata
from datetime import date

import requests

from src import config
from src.download import fred_data, inegi_data, inegi_name, redact, sie_metadata

FIELDS = ["key", "source", "id", "titulo", "periodicidad", "unidad",
          "fecha_inicio", "fecha_fin", "rol", "fecha_consulta", "resultado"]


def normalize(text: str) -> str:
    """Minúsculas y sin acentos, para comparar títulos sin falsos negativos."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def compact(text: str) -> str:
    """Normaliza y quita espacios: el SIE a veces escribe títulos como 'I n d i c e'."""
    return "".join(normalize(text).split())


def matches(title: str, expected: list) -> bool:
    return all(compact(word) in compact(title) for word in expected)


def base_row(spec: dict) -> dict:
    return {"key": spec["key"], "source": spec["source"], "id": spec["id"] or "",
            "rol": spec["role"], "fecha_consulta": date.today().isoformat()}


def validate_sie(spec: dict, session) -> dict:
    meta = sie_metadata(spec["id"], session)
    title = " ".join((meta.get("titulo") or "").split())  # quita espacios dobles
    return {**base_row(spec), "titulo": title,
            "periodicidad": meta.get("periodicidad", ""), "unidad": meta.get("unidad", ""),
            "fecha_inicio": meta.get("fechaInicio", ""), "fecha_fin": meta.get("fechaFin", ""),
            "resultado": "OK" if matches(title, spec["expected"]) else "REVISAR"}


INEGI_FREQ = {"8": "Mensual"}  # INEGI devuelve códigos; se amplía si aparecen otros


def validate_inegi(spec: dict, session) -> dict:
    # Los datos son lo esencial: si esta consulta falla, el ID está mal
    series = inegi_data(spec["id"], session, recent=True).json()["Series"][0]
    last = series["OBSERVATIONS"][0]["TIME_PERIOD"] if series.get("OBSERVATIONS") else ""
    # El nombre es un complemento: si el catálogo no responde, se verifica a mano
    try:
        title = inegi_name(spec["id"], session)
        if not spec["expected"]:
            result = "MANUAL"  # sin palabras esperadas no hay contra qué comparar
        else:
            result = "OK" if matches(title, spec["expected"]) else "REVISAR"
    except Exception:
        title, result = "(nombre no disponible; verificar en el Constructor de consultas)", "MANUAL"
    if spec.get("label"):
        title = f"{spec['label']} [API: {title}]"
    freq = series.get("FREQ", "")
    return {**base_row(spec), "titulo": title, "periodicidad": INEGI_FREQ.get(freq, freq),
            "unidad": series.get("UNIT", ""), "fecha_inicio": "", "fecha_fin": last,
            "resultado": result}


def validate_fred(spec: dict, session) -> dict:
    lines = fred_data(spec["id"], session).text.strip().splitlines()
    first = lines[1].split(",")[0] if len(lines) > 1 else ""
    last = lines[-1].split(",")[0] if len(lines) > 1 else ""
    return {**base_row(spec), "titulo": "(verificar en fred.stlouisfed.org/series/" + spec["id"] + ")",
            "periodicidad": "Mensual", "unidad": "Porcentaje",
            "fecha_inicio": first, "fecha_fin": last, "resultado": "MANUAL"}


VALIDATORS = {"SIE": validate_sie, "INEGI": validate_inegi, "FRED": validate_fred}


def validate_all(session=None) -> list:
    session = session or requests.Session()
    rows = []
    for spec in config.SERIES:
        if not spec["id"]:
            rows.append({**base_row(spec), "resultado": "PENDIENTE (sin ID)"})
            continue
        try:
            rows.append(VALIDATORS[spec["source"]](spec, session))
        except Exception as exc:
            rows.append({**base_row(spec), "resultado": f"ERROR: {redact(str(exc))[:120]}"})
    return rows


def write_dictionary(rows: list):
    config.REPORTS.mkdir(parents=True, exist_ok=True)
    path = config.REPORTS / "diccionario_datos.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel lee bien los acentos
        writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def main() -> int:
    rows = validate_all()
    for r in rows:
        print(f"[{r['resultado']}] {r['key']:<14} {r['id']:<10} {r.get('titulo', '')[:70]}")
        if r.get("fecha_fin"):
            print(f"{'':>17}periodo: {r.get('fecha_inicio', '')} -> {r['fecha_fin']}"
                  f" | {r.get('periodicidad', '')} | {r.get('unidad', '')}")
    path = write_dictionary(rows)
    print(f"\nDiccionario de datos: {path.relative_to(config.ROOT)}")
    # Código de salida 1 si algo requiere revisión: útil si después lo automatizas
    return 0 if all(r["resultado"] in ("OK", "MANUAL") for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
