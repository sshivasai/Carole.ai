import os
import sys
import asyncio
import uuid
import json
from pathlib import Path

# Add backend directory to sys.path so we can import 'core'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.memory.database import init_db, get_db, engine
from core.api.crud_routes import seed_demo
from core.memory.models import User, Project, Team, Agent
from core.memory.lancedb_client import lancedb_client
from sqlalchemy import select

async def main():
    print("--- Test 1: SQLite Initialization ---")
    await init_db(force_recreate=True)
    
    db_path = str(Path.home() / ".carole" / "carole.db")
    if not os.path.exists(db_path):
        # Maybe it was created relative to the root workspace
        workspace_db = str(Path.home() / ".carole" / "carole.db")
        if os.path.exists(workspace_db):
            print(f"✅ SQLite initialized at {workspace_db}")
        else:
            print(f"❌ SQLite file not found at {db_path} or {workspace_db}")
    else:
        print(f"✅ SQLite initialized at {db_path}")

    print("\n--- Test 2: Database Seeding ---")
    async for db in get_db():
        res = await seed_demo(db)
        print(f"Seed Result: {res}")
        
        # Verify
        users = (await db.execute(select(User))).scalars().all()
        projects = (await db.execute(select(Project))).scalars().all()
        teams = (await db.execute(select(Team))).scalars().all()
        agents = (await db.execute(select(Agent))).scalars().all()
        
        print(f"Users count: {len(users)}")
        print(f"Projects count: {len(projects)}")
        print(f"Teams count: {len(teams)}")
        print(f"Agents count: {len(agents)}")
        
        if len(users) > 0 and len(projects) > 0 and len(teams) > 0 and len(agents) > 0:
            print("✅ Database seeding verified!")
        else:
            print("❌ Database seeding failed verification!")
            
        break

    print("\n--- Test 3: LanceDB ---")
    dummy_project_id = str(uuid.uuid4())
    dummy_team_id = str(uuid.uuid4())
    dummy_vector = [0.1] * 384  # Replace with appropriate dimension if needed, standard embedding
    # Lancedb client in backend uses default 384 dim for embeddings if not specified, 
    # but let's check what `lancedb_client.insert_learning` expects.
    try:
        await lancedb_client.insert_learning(
            project_id=dummy_project_id,
            team_id=dummy_team_id,
            task_summary="Test task",
            lesson_rule="Test rule",
            vector=dummy_vector
        )
        print("✅ LanceDB insertion successful!")
        
        results = await lancedb_client.search_learnings(
            project_id=dummy_project_id,
            query_vector=dummy_vector,
            limit=1
        )
        print(f"Search Results: {results}")
        if len(results) > 0 and results[0]["task_summary"] == "Test task":
            print("✅ LanceDB semantic retrieval successful!")
        else:
            print("❌ LanceDB semantic retrieval failed to match!")
            
        lancedb_path = str(Path.home() / ".carole" / "vector_store")
        if os.path.exists(lancedb_path):
            print(f"✅ LanceDB vector_store found at {lancedb_path}")
        else:
            print(f"❌ LanceDB vector_store not found at {lancedb_path}")
            
    except Exception as e:
        print(f"❌ LanceDB Error: {e}")

    print("\n--- Test 4: JSON Code Graph ---")
    try:
        from core.knowledge.code_graph import code_graph
        code_graph.parse_file("backend/main.py")
        
        graph_path = str(Path.home() / ".carole" / "code_graph.json")
        if os.path.exists(graph_path):
            with open(graph_path, "r") as f:
                data = json.load(f)
                if "nodes" in data and "links" in data:
                    print("✅ JSON Code Graph generated and valid!")
                else:
                    print("❌ JSON Code Graph format invalid!")
        else:
            print(f"❌ JSON Code Graph not found at {graph_path}")
    except Exception as e:
        print(f"❌ Code Graph Error: {e}")

    # Dispose engine
    await engine.dispose()
    
if __name__ == "__main__":
    asyncio.run(main())
