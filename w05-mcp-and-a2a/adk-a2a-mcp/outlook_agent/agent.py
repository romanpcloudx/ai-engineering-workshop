"""Agent B: Outlook specialist exposed through A2A."""

from __future__ import annotations

import os
from pathlib import Path

from composio import SESSION_PRESET_DIRECT_TOOLS, Composio
from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import (
    McpToolset,
    StreamableHTTPConnectionParams,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / '.env')
load_dotenv(PROJECT_DIR / '.env')

TOOLKIT = 'outlook'
ALLOWED_TOOL = 'OUTLOOK_SEND_EMAIL'


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f'Missing required environment variable: {name}')
    return value


# Composio no publica una URL de MCP fija: se crea una sesion y esa sesion
# devuelve su propio endpoint. Aqui se acota el catalogo (>200 tools) a una
# sola, sobre la cuenta de Outlook ya conectada.
session = Composio(api_key=_required('COMPOSIO_API_KEY')).sessions.create(
    user_id=_required('COMPOSIO_USER_ID'),
    toolkits=[TOOLKIT],
    tools={TOOLKIT: {'enable': [ALLOWED_TOOL]}},
    auth_configs={TOOLKIT: _required('COMPOSIO_AUTH_CONFIG_ID')},
    connected_accounts={TOOLKIT: [_required('COMPOSIO_CONNECTED_ACCOUNT_ID')]},
    # Expone las tools directamente, sin las meta-tools de busqueda.
    session_preset=SESSION_PRESET_DIRECT_TOOLS,
    mcp=True,
)

outlook_tools = McpToolset(
    connection_params=StreamableHTTPConnectionParams(
        url=session.mcp.url,
        headers={
            key: value
            for key, value in (session.mcp.headers or {}).items()
            if value is not None
        },
    ),
    # La sesion ya viene restringida; ADK vuelve a filtrar antes de que las
    # tools lleguen al modelo.
    tool_filter=[ALLOWED_TOOL],
)

root_agent = LlmAgent(
    model=os.getenv('ADK_MODEL', 'gemini-3.7-flash'),
    name='outlook_email_agent',
    description=(
        'Remote Outlook specialist. Sends email only when given recipients, '
        'subject, body, and an explicit instruction to send.'
    ),
    instruction=(
        'You are Agent B, a specialist that sends Outlook email. '
        f'Your only available operation is {ALLOWED_TOOL}. '
        'Never invent recipients, subject, or body. If any is missing, ask '
        'for it. Sending email is an external side effect: call the tool only '
        'when the current request explicitly asks to send the fully specified '
        'email. After the call, report success or the exact error concisely.'
    ),
    tools=[outlook_tools],
)

# La exposicion A2A la hace `adk web --a2a`: al encontrar el agent.json de esta
# carpeta, publica el agente en /a2a/outlook_agent. Por eso aca no hay servidor.
