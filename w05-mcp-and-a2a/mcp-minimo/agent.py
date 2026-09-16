"""MCP client + LLM loop.

The model never talks to the server. It asks for a function; this process
translates that into MCP `tools/call`.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import TextContent
from openai import AsyncOpenAI

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')

MCP_URL = 'http://127.0.0.1:8000/mcp'

SYSTEM_PROMPT = (
    'You are a helpful assistant. '
    'You have tools; use them only when they are needed to answer. '
    'Greetings, chit-chat, and anything that is not arithmetic: reply '
    'directly, without calling a tool.'
)


def _openai_tools(mcp_tools: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            'type': 'function',
            'function': {
                'name': tool.name,
                'description': tool.description or '',
                'parameters': tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def _tool_text(result: Any) -> str:
    parts = [
        content.text
        if isinstance(content, TextContent)
        else json.dumps(content.model_dump(), ensure_ascii=False)
        for content in result.content
    ]
    prefix = 'MCP tool error: ' if result.isError else ''
    return prefix + '\n'.join(parts)


async def step(
    llm: AsyncOpenAI,
    session: ClientSession,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> str:
    for _ in range(4):
        response = await llm.chat.completions.create(
            model='deepseek-chat',
            messages=messages,
            tools=tools or None,
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        if not message.tool_calls:
            return message.content or ''

        for call in message.tool_calls:
            arguments = json.loads(call.function.arguments)
            print(f'[MCP] tools/call {call.function.name}({arguments})')
            result = await session.call_tool(call.function.name, arguments=arguments)
            print(f'[result] {result}')
            text = _tool_text(result)
            print(f'[MCP] result: {text}')
            messages.append(
                {
                    'role': 'tool',
                    'tool_call_id': call.id,
                    'content': text,
                }
            )

    return 'Error: too many tool steps.'


async def chat(session: ClientSession) -> None:
    listed = await session.list_tools()
    tools = _openai_tools(listed.tools)
    print('[MCP] discovered tools:', ', '.join(t['function']['name'] for t in tools))

    api_key = os.getenv('DEEPSEEK_API_KEY')
    if not api_key:
        raise RuntimeError('DEEPSEEK_API_KEY is not configured.')

    llm = AsyncOpenAI(api_key=api_key, base_url='https://api.deepseek.com')
    messages: list[dict[str, Any]] = [{'role': 'system', 'content': SYSTEM_PROMPT}]

    print('Chat with the agent. Use `exit` to quit.')
    while True:
        question = input('user > ').strip()
        if question.lower() in {'exit', 'q'}:
            return
        if not question:
            continue

        messages.append({'role': 'user', 'content': question})
        answer = await step(llm, session, messages, tools)
        print(f'agent > {answer}')


async def main() -> None:
    print(f'[MCP] connecting to {MCP_URL}')
    connected = False
    try:
        # En mcp 1.x el transport entrega (read, write, get_session_id).
        async with (
            streamable_http_client(MCP_URL) as (read, write, _),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            connected = True
            await chat(session)
    except Exception as exc:
        if connected:
            raise
        raise RuntimeError(
            f'No MCP server at {MCP_URL}. Start it in another terminal:\n'
            r'  python .\w05-mcp-and-a2a\mcp-minimo\server.py'
        ) from exc


if __name__ == '__main__':
    asyncio.run(main())
