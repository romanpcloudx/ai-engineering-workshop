"""Agente bancario de W03, con traces a Langfuse cuando hay credenciales.

La instrumentacion tiene que correr ANTES de que ADK ejecute el agente.
Por eso vive aca (al importar el paquete), no en agent.py.
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Carga KEY=VALUE sin depender de python-dotenv."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


_AGENT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _AGENT_DIR.parent

_load_dotenv(_AGENT_DIR / ".env")
_load_dotenv(_REPO_ROOT / ".env")

# ADK / Gemini esperan GOOGLE_API_KEY; el workshop a veces usa GOOGLE_GENAI_API_KEY.
if not os.environ.get("GOOGLE_API_KEY") and os.environ.get("GOOGLE_GENAI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.environ["GOOGLE_GENAI_API_KEY"]

# Compat: algunas versiones leen LANGFUSE_HOST en lugar de LANGFUSE_BASE_URL.
if os.environ.get("LANGFUSE_BASE_URL") and not os.environ.get("LANGFUSE_HOST"):
    os.environ["LANGFUSE_HOST"] = os.environ["LANGFUSE_BASE_URL"]


def _setup_langfuse() -> None:
    public = os.environ.get("LANGFUSE_PUBLIC_KEY", "").strip()
    secret = os.environ.get("LANGFUSE_SECRET_KEY", "").strip()
    if not public or not secret or public.startswith("pk-lf-..."):
        print(
            "[w03] Langfuse no configurado. Completa LANGFUSE_PUBLIC_KEY / "
            "LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL en .env para enviar traces. "
            "ADK Web sigue andando igual."
        )
        return

    try:
        from langfuse import get_client
        from openinference.instrumentation.google_adk import GoogleADKInstrumentor
    except ImportError:
        print(
            "[w03] Faltan dependencias de Langfuse. "
            "pip install -r w03_tracing_and_observability/requirements.txt"
        )
        return

    langfuse = get_client()
    if langfuse.auth_check():
        print("[w03] Langfuse OK — traces visibles en el dashboard.")
    else:
        print(
            "[w03] Langfuse auth fallo. Revisa LANGFUSE_PUBLIC_KEY / "
            "LANGFUSE_SECRET_KEY / LANGFUSE_BASE_URL."
        )
        return

    instrumentor = GoogleADKInstrumentor()
    if not instrumentor.is_instrumented_by_opentelemetry:
        instrumentor.instrument()


_setup_langfuse()

from . import agent  # noqa: E402  — despues de instrumentar
