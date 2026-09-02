import pytest
from pathlib import Path
from core.knowledge.code_graph import CodeGraph
from core.knowledge.ast_parser import ASTChunk

@pytest.mark.asyncio
async def test_generate_repo_map_empty(tmp_path):
    cg = CodeGraph(workspace_root=str(tmp_path))
    repo_map = await cg.generate_repo_map()
    assert repo_map == ""


@pytest.mark.asyncio
async def test_generate_repo_map_multi_file(tmp_path):
    # Setup sample files
    models_file = tmp_path / "models.py"
    models_file.write_text("""
class UserPreferences:
    \"\"\"User travel preferences.\"\"\"
    def __init__(self, budget: float):
        self.budget = budget

class ItineraryResult:
    pass
""", encoding="utf-8")

    planner_file = tmp_path / "planner.py"
    planner_file.write_text("""
import models

def calculate_itinerary(user_id: str, prefs: models.UserPreferences) -> models.ItineraryResult:
    return models.ItineraryResult()

def score_destination(dest: str, budget: float) -> float:
    return 1.0
""", encoding="utf-8")

    cg = CodeGraph(workspace_root=str(tmp_path))
    await cg.build_graph()

    repo_map = await cg.generate_repo_map(max_tokens=500)
    assert "<repo-map>" in repo_map
    assert "</repo-map>" in repo_map
    assert "UserPreferences" in repo_map
    assert "calculate_itinerary" in repo_map
    assert "models.py:" in repo_map
    assert "planner.py:" in repo_map


@pytest.mark.asyncio
async def test_generate_repo_map_budget_cap(tmp_path):
    # Create multiple files
    for i in range(15):
        f = tmp_path / f"service_{i}.py"
        f.write_text(f"""
class Service{i}:
    def run_job_{i}(self):
        pass
    def process_{i}(self):
        pass
""", encoding="utf-8")

    cg = CodeGraph(workspace_root=str(tmp_path))
    await cg.build_graph()

    # Small budget
    repo_map = await cg.generate_repo_map(max_tokens=60)
    # Token length roughly <= 60 * 4 chars
    assert len(repo_map) < 600
