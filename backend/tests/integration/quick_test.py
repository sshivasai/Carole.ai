import asyncio
import websockets

async def test():
    try:
        async with websockets.connect('ws://localhost:8000/ws/chat/123') as ws:
            print('Connected!')
    except Exception as e:
        print(f'Error: {e}')

asyncio.run(test())
