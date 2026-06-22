import sqlite3
import os
db_path = os.path.expanduser("~/.carole/carole.db")
c = sqlite3.connect(db_path)
for row in c.execute("SELECT id, name, role FROM agents"):
    print(row)
