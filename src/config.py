"""Configuración central del proyecto: rutas, URLs base y catálogo de series.

Todo lo que puede cambiar (IDs, fechas, fuentes) vive aquí, para no tocar
la lógica de descarga cuando haya que corregir un dato.
"""
from pathlib import Path

# --- Rutas (relativas a la raíz del repositorio, sin importar desde dónde se ejecute) ---
ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"

# --- Periodo de análisis ---
START_DATE = "2008-01-01"  # formato aaaa-mm-dd que exige el SIE

# --- URLs base de las APIs ---
SIE_BASE = "https://www.banxico.org.mx/SieAPIRest/service/v1"
INEGI_BASE = "https://inegi.org.mx/app/api/indicadores/desarrolladores/jsonxml"  # igual que el Constructor de consultas
INEGI_SOURCE = "BIE-BISE"  # tal como aparece en la URL que genera el Constructor de consultas
INEGI_GEO = "00"      # 00 = nacional
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"  # no requiere API key

# --- Catálogo de series ---
# expected: palabras que DEBEN aparecer en el título oficial de la serie.
# Si no aparecen, validate_ids.py marca el ID como sospechoso.
# expected vacío = validación manual (la API no da un título útil).
# label: nombre completo para el diccionario cuando el título oficial es poco descriptivo.
# status: "por validar" hasta que validate_ids.py lo confirme; luego cámbialo a "validado".
SERIES = [
    {
        "key": "tiie28",
        "source": "SIE",
        "id": "SF60648",  # TIIE 28 días por fecha de determinación
        "expected": ["28 dias"],
        "role": "Variable objetivo (periodo histórico)",
        "status": "validado",
    },
    {
        "key": "tasa_objetivo",
        "source": "SIE",
        "id": "SF61745",
        "expected": ["objetivo"],
        "role": "Ancla de política monetaria",
        "status": "validado",
    },
    {
        "key": "tiie_fondeo",
        "source": "SIE",
        "id": "SF331451",  # mediana ponderada por volumen; disponible desde 2006
        "expected": ["fondeo"],
        "role": "Variable objetivo (muestra completa, sin quiebre metodológico)",
        "status": "validado",
    },
    {
        "key": "fix",
        "source": "SIE",
        "id": "SF43718",
        "expected": ["fix"],
        "role": "Exógena: tipo de cambio",
        "status": "validado",
    },
    {
        "key": "inpc",
        "source": "SIE",
        "id": "SP1",  # INPC, índice general por objeto del gasto, nacional
        "expected": ["ipc", "indice general"],
        "role": "Exógena: inflación (se calcula la variación anual)",
        "status": "validado",
    },
    {
        "key": "igae",
        "source": "INEGI",
        "id": "737219",
        "expected": [],  # el BIE solo devuelve la hoja del árbol ("Índice"): se valida a mano
        "label": "IGAE total, serie desestacionalizada, índice base 2018 (BIE)",
        "role": "Exógena: actividad económica",
        "status": "por validar",
    },
    {
        "key": "fedfunds",
        "source": "FRED",
        "id": "FEDFUNDS",
        "expected": [],  # FRED sin API key no devuelve título; se verifica a mano
        "role": "Exógena externa: tasa de la Fed",
        "status": "por validar",
    },
]
