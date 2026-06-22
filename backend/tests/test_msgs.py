import sqlite3
import os

db_path = os.path.expanduser("~/.carole/carole.db")
c = sqlite3.connect(db_path)
rows = c.execute("SELECT id, text, created_at, sequence FROM messages ORDER BY created_at ASC, sequence ASC").fetchall()
for r in rows:
    print(r)
