"""Levanta la UI de ADK mostrando solo el trafico A2A, en formato legible.

Equivale a `adk web --a2a .`, pero en vez de prender DEBUG en todo (que vuelca
el evento entero en una sola linea de JSON) deja en DEBUG unicamente el logger
que imprime las tasks A2A.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from google.adk.cli.fast_api import get_fast_api_app


HERE = Path(__file__).resolve().parent
load_dotenv(HERE / '.env')

HOST = os.getenv('ADK_WEB_HOST', '127.0.0.1')
PORT = int(os.getenv('ADK_WEB_PORT', '8000'))

# Logger que imprime "A2A Request/Response" con task id, context id y estado.
A2A_LOGGER = 'google_adk.google.adk.agents.remote_a2a_agent'
# Logger que vuelca el evento completo serializado; es el que ensucia todo.
NOISY_LOGGER = 'google_adk.google.adk.cli.api_server'


class A2AOnly(logging.Filter):
    """Deja pasar los INFO/WARNING normales y, en DEBUG, solo lo de A2A."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno > logging.DEBUG:
            return True
        return record.name == A2A_LOGGER


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    handler.addFilter(A2AOnly())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)

    logging.getLogger(A2A_LOGGER).setLevel(logging.DEBUG)
    logging.getLogger(NOISY_LOGGER).setLevel(logging.WARNING)
    for noisy in (
        'httpx',
        'httpcore',
        'uvicorn.access',
        'google_genai',
        # Vuelca la Agent Card entera cada vez que la resuelve.
        'a2a.client.card_resolver',
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)


_configure_logging()

app = get_fast_api_app(
    agents_dir=str(HERE),
    web=True,
    a2a=True,
    host=HOST,
    port=PORT,
)


if __name__ == '__main__':
    print(f'[ADK] UI en http://{HOST}:{PORT}')
    print(f'[A2A] Agent B en http://{HOST}:{PORT}/a2a/outlook_agent')
    uvicorn.run(app, host=HOST, port=PORT, log_config=None)
