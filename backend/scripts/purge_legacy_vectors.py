"""
backend/scripts/purge_legacy_vectors.py

Reconciles LanceDB with SQLite by removing any orphaned vector records
whose IDs do not exist in the active SQLite database.
"""

import sys
import sqlite3
from pathlib import Path

backend_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_root))

from core.config import CAROLE_HOME_DIR
import lancedb

def reconcile_and_purge():
    # 1. Fetch valid IDs from SQLite
    db_path = CAROLE_HOME_DIR / "carole.db"
    valid_ids = set()
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("SELECT id FROM learnings")
        valid_ids = {str(r[0]) for r in c.fetchall()}
        conn.close()

    print(f"Valid Learning IDs in SQLite: {len(valid_ids)}")

    # 2. Connect to LanceDB
    uri = str(CAROLE_HOME_DIR / "vector_store")
    print(f"Connecting to LanceDB at: {uri}")
    db = lancedb.connect(uri)

    tables = db.table_names()
    if "learnings" not in tables:
        print("Table 'learnings' does not exist in LanceDB.")
        return

    table = db.open_table("learnings")
    records = table.to_arrow().to_pylist()
    print(f"Total vector records in LanceDB before purge: {len(records)}")

    # 3. Find orphaned IDs
    orphaned_ids = [str(r.get("id")) for r in records if str(r.get("id")) not in valid_ids]
    print(f"Orphaned vector records to purge: {len(orphaned_ids)}")

    if not orphaned_ids:
        print("LanceDB is already 100% synchronized with SQLite.")
        return

    if len(valid_ids) == 0:
        # All records are orphans — drop the table clean so it's fresh
        print("All records are orphaned. Dropping table 'learnings' to create clean state.")
        db.drop_table("learnings")
        print("Table 'learnings' successfully dropped and cleaned.")
    else:
        for oid in orphaned_ids:
            try:
                table.delete(f"id = '{oid}'")
            except Exception as e:
                print(f"Error deleting id {oid}: {e}")

    # Verify
    tables_after = db.table_names()
    if "learnings" in tables_after:
        remaining = db.open_table("learnings").to_arrow().to_pylist()
        print(f"LanceDB vector records remaining: {len(remaining)}")
    else:
        print("LanceDB 'learnings' table is clean and will be lazily recreated on next legitimate learning insertion.")

if __name__ == "__main__":
    reconcile_and_purge()
