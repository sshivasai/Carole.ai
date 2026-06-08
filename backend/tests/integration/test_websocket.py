import asyncio
import json
import websockets
import urllib.request
import urllib.parse
from uuid import UUID

API_URL = "http://localhost:8000"

def get_team_id():
    # Try to seed first
    req = urllib.request.Request(f"{API_URL}/api/seed", method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode())
            if res.get("status") == "seeded":
                print(f"Seeded new environment. Team ID: {res['team_id']}")
                return res["team_id"]
    except Exception as e:
        print(f"Seed failed or already seeded: {e}")

    # If already seeded or failed, fetch from projects/teams
    print("Fetching existing project and team...")
    req = urllib.request.Request(f"{API_URL}/api/projects")
    with urllib.request.urlopen(req) as response:
        projects = json.loads(response.read().decode())
        if not projects:
            raise Exception("No projects found.")
        project_id = projects[0]["id"]
        
    req = urllib.request.Request(f"{API_URL}/api/teams/{project_id}")
    with urllib.request.urlopen(req) as response:
        teams = json.loads(response.read().decode())
        if not teams:
            raise Exception("No teams found for project.")
        return teams[0]["id"]

async def test_websocket():
    team_id = get_team_id()
    print(f"Using Team ID: {team_id}")

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
            
            for i in range(15):
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                    try:
                        parsed = json.loads(response)
                        print(f"Received [{i+1}/15]: {json.dumps(parsed, indent=2)}")
                    except json.JSONDecodeError:
                        print(f"Received [{i+1}/15] (raw): {response}")
                except asyncio.TimeoutError:
                    print(f"Timeout waiting for message {i+1}")
                    break
                    
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_websocket())
