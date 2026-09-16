"""MCP server: one tool, over Streamable HTTP.

Independent process. Clients connect to MCP_URL; this file does not launch them.
"""

from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

HOST = '127.0.0.1'
PORT = 8000
MCP_PATH = '/mcp'

# En mcp 1.x el host/puerto son settings del servidor, no argumentos de run().
mcp = FastMCP(
    'calculator',
    instructions='Arithmetic helpers for agents.',
    host=HOST,
    port=PORT,
    streamable_http_path=MCP_PATH,
)


@mcp.tool()
def add(
    a: Annotated[int, Field(description='First number to add.')],
    b: Annotated[int, Field(description='Second number to add.')],
) -> int:
    """Add two integers and return the sum."""
    print(f'[MCP server] add({a}, {b})')
    return a + b


if __name__ == '__main__':
    print(f'[MCP] calculator listening on http://{HOST}:{PORT}{MCP_PATH}')
    mcp.run(transport='streamable-http')
