import os
import uuid
import lancedb
from typing import List, Optional, Dict, Any

# Ensure .carole directory exists
os.makedirs(".carole", exist_ok=True)

class LanceDBClient:
    def __init__(self, uri: str = ".carole/vector_store"):
        self.uri = uri
        self.db = lancedb.connect(self.uri)
        self.table_name = "learnings"
        
        # Initialize table if it doesn't exist
        if self.table_name not in self.db.table_names():
            # Define schema using pyarrow or let LanceDB infer from first insertion
            # We'll rely on an empty insertion or just wait for the first real insertion
            pass
            
    def get_or_create_table(self):
        # In LanceDB, you can create a table by providing data.
        pass

    async def insert_learning(self, project_id: str, task_summary: str, lesson_rule: str, vector: List[float], team_id: Optional[str] = None):
        """Insert a new learning into the vector store."""
        data = [{
            "id": str(uuid.uuid4()),
            "project_id": project_id,
            "team_id": team_id if team_id else "",
            "task_summary": task_summary,
            "lesson_rule": lesson_rule,
            "vector": vector
        }]
        
        if self.table_name in self.db.table_names():
            table = self.db.open_table(self.table_name)
            table.add(data)
        else:
            self.db.create_table(self.table_name, data=data)

    async def search_learnings(self, vector: List[float], project_id: str, team_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for similar learnings."""
        if self.table_name not in self.db.table_names():
            return []
            
        table = self.db.open_table(self.table_name)
        
        # Build filter string
        # We want to match project_id and (team_id is empty OR team_id matches)
        filter_str = f"project_id = '{project_id}'"
        
        # NOTE: If we want to strictly match team_id or global (team_id=""), we can add it:
        if team_id:
            filter_str += f" AND (team_id = '{team_id}' OR team_id = '')"
        else:
            # If no team specified, maybe only return project-level? 
            # Or return all? Usually if team_id is None we want project-wide (team_id == "")
            filter_str += " AND team_id = ''"

        results = table.search(vector).where(filter_str).limit(limit).to_list()
        return results

lancedb_client = LanceDBClient()
