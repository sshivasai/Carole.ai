import sqlite3
import os

db_path = os.path.expanduser("~/.carole/carole.db")
if not os.path.exists(db_path):
    print(f"DB not found at {db_path}")
else:
    c = sqlite3.connect(db_path)
    print(c.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall())
