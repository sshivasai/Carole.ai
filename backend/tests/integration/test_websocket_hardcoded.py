import asyncio
import json
import websockets
import urllib.request

async def test_websocket():
    team_id = "02b5e7bb-5c50-4cc0-89d2-e48ddcdd5773"

    uri = f"ws://localhost:8000/ws/chat/{team_id}?agent_id=human&agent_name=Admin"
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"Connected to {uri}")


            
            payload = {
                "text": "Hey @Archer, what are you up to?",
                "sender_id": "human",
                "sender_name": "Admin"
            }
            
            print(f"Sending payload: {json.dumps(payload, indent=2)}")
            await websocket.send(json.dumps(payload))
            
            print("Listening for responses...")
            
            for i in range(10):
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                    try:
                        parsed = json.loads(response)
                        print(f"Received [{i+1}/10]: {json.dumps(parsed, indent=2)}")
                    except json.JSONDecodeError:
                        print(f"Received [{i+1}/10] (raw): {response}")
                except asyncio.TimeoutError:
                    print(f"Timeout waiting for message {i+1}")
                    break
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
