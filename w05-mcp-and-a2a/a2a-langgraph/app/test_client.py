import json
import logging

import httpx

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import display_agent_card, new_text_message
from a2a.types import Role, SendMessageRequest
from a2a.utils.constants import AGENT_CARD_WELL_KNOWN_PATH
from google.protobuf.json_format import MessageToDict


BASE_URL = 'http://127.0.0.1:10000'


def _dump(message) -> None:
    print(json.dumps(MessageToDict(message), indent=2, ensure_ascii=False))


async def last_task(client, request):
    task = None
    async for chunk in client.send_message(request):
        _dump(chunk)
        if chunk.HasField('task'):
            task = chunk.task
    return task


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    async with httpx.AsyncClient(timeout=120) as httpx_client:
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=BASE_URL,
        )
        logger.info(
            'Fetching public agent card from %s%s',
            BASE_URL,
            AGENT_CARD_WELL_KNOWN_PATH,
        )
        public_card = await resolver.get_agent_card()
        display_agent_card(public_card)

        config = ClientConfig(streaming=False, httpx_client=httpx_client)
        client = await create_client(agent=public_card, client_config=config)
        logger.info('Non-streaming client initialized.')

        print('\n--- Single turn ---')
        request = SendMessageRequest(
            message=new_text_message(
                'how much is 10 USD in INR?',
                role=Role.ROLE_USER,
            )
        )
        await last_task(client, request)

        print('\n--- Multi-turn ---')
        request = SendMessageRequest(
            message=new_text_message(
                'How much is the exchange rate for 1 USD?',
                role=Role.ROLE_USER,
            )
        )
        task = await last_task(client, request)
        if task is None:
            raise RuntimeError('Multi-turn request did not return a task.')

        follow_up = SendMessageRequest(
            message=new_text_message(
                'CAD',
                role=Role.ROLE_USER,
                task_id=task.id,
                context_id=task.context_id,
            )
        )
        await last_task(client, follow_up)

        print('\n--- Streaming ---')
        # Same httpx client on purpose: closing an a2a client would close it
        # for everyone, so the `async with` block above owns its lifetime.
        stream_client = await create_client(
            agent=public_card,
            client_config=ClientConfig(streaming=True, httpx_client=httpx_client),
        )
        stream_request = SendMessageRequest(
            message=new_text_message(
                'how much is 10 USD in INR?',
                role=Role.ROLE_USER,
            )
        )
        async for chunk in stream_client.send_message(stream_request):
            _dump(chunk)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())
