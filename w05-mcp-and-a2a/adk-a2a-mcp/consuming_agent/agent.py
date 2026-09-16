"""Agent A: generalist that delegates Outlook email work over A2A."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import (
    AGENT_CARD_WELL_KNOWN_PATH,
    RemoteA2aAgent,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPO_ROOT / '.env')
load_dotenv(PROJECT_DIR / '.env')

# `adk web --a2a` monta cada agente con agent.json bajo /a2a/<carpeta>, asi que
# por defecto Agent B vive en el mismo proceso que este. Si lo corres aparte
# (por ejemplo `adk api_server --a2a --port 8001`), cambia OUTLOOK_AGENT_URL.
OUTLOOK_AGENT_URL = os.getenv(
    'OUTLOOK_AGENT_URL',
    'http://127.0.0.1:8000/a2a/outlook_agent',
).rstrip('/')

outlook_agent = RemoteA2aAgent(
    name='outlook_email_agent',
    description=(
        'Remote specialist for sending email through Outlook. Delegate only '
        'requests whose goal is to send an Outlook email.'
    ),
    agent_card=f'{OUTLOOK_AGENT_URL}{AGENT_CARD_WELL_KNOWN_PATH}',
    # Requests ADK's current A2A extension and executor behavior.
    use_legacy=False,
)

root_agent = LlmAgent(
    model=os.getenv('ADK_MODEL', 'gemini-3.7-flash'),
    name='generalist_agent',
    description=(
        'General assistant that can delegate Outlook email sending to a '
        'remote A2A agent.'
    ),
    instruction=(
        'You are Agent A, a general assistant. Answer ordinary questions '
        'yourself. When the user explicitly wants to send an Outlook email, '
        'delegate the complete request to outlook_email_agent. Do not claim '
        'an email was sent unless the remote agent confirms it. If recipient, '
        'subject, body, or intent to send is missing, gather that information '
        'before delegating.'
    ),
    sub_agents=[outlook_agent],
)
