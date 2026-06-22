import requests
msgs = requests.get('http://localhost:8000/api/messages/1c63f8746df34bacbf3b5b9b2126fa01?limit=10').json()
for m in msgs:
    if m.get('reasoning'):
        print(f"--- MSG {m['id']} ---")
        print(m['reasoning'][:200])
        print("...")
