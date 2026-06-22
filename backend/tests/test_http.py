import urllib.request
import json
import sys

try:
    resp = urllib.request.urlopen('http://localhost:8000/api/teams/b1b9e072-c2e3-47a3-ab2d-05df3c36c61f')
    # wait, I don't know the team_id. Let's just fetch it from sqlite directly.
except Exception:
    pass
