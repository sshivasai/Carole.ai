import os
import shutil
import tempfile
from pathlib import Path
import pytest
from httpx import AsyncClient

from core.skills.skill_parser import SkillParser, SkillDefinition
from core.skills.skill_manager import SkillManager, _SKILL_STATE_OVERRIDES


@pytest.fixture
def temp_skills_workspace():
    temp_dir = tempfile.mkdtemp(prefix="carole_test_skills_")
    ws_path = Path(temp_dir)
    
    # Create .agents/skills/data-analyst/SKILL.md
    skills_dir = ws_path / ".agents" / "skills" / "data-analyst"
    skills_dir.mkdir(parents=True)
    scripts_dir = skills_dir / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "run_analysis.py").write_text("# Python script", encoding="utf-8")
    
    skill_md = skills_dir / "SKILL.md"
    skill_md.write_text(
        "---\n"
        "name: data-analyst\n"
        "description: Expert in time-series forecasting and dataset summarization\n"
        "tools:\n"
        "  - run_command\n"
        "  - read_resource\n"
        "dependencies:\n"
        "  - pandas\n"
        "author: DeepMind\n"
        "version: 2.1.0\n"
        "---\n"
        "\n"
        "# Data Analyst Skill\n"
        "Follow these rules whenever analyzing tabular datasets:\n"
        "1. Always compute summary statistics.\n"
        "2. Check for missing values before training models.\n",
        encoding="utf-8"
    )

    yield ws_path
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_skill_parser_valid_file(temp_skills_workspace):
    skill_path = temp_skills_workspace / ".agents" / "skills" / "data-analyst" / "SKILL.md"
    parsed = SkillParser.parse_skill_file(skill_path, source="project")
    
    assert parsed is not None
    assert parsed.name == "data-analyst"
    assert "time-series" in parsed.description
    assert parsed.tools == ["run_command", "read_resource"]
    assert parsed.dependencies == ["pandas"]
    assert parsed.author == "DeepMind"
    assert parsed.version == "2.1.0"
    assert parsed.source == "project"
    assert "Always compute summary statistics" in parsed.instructions
    assert "run_analysis.py" in parsed.scripts


def test_skill_parser_missing_or_invalid():
    assert SkillParser.parse_skill_file(Path("/nonexistent/SKILL.md")) is None


def test_discover_filesystem_skills(temp_skills_workspace):
    discovered = SkillManager.discover_filesystem_skills(workspace_root=temp_skills_workspace)
    names = [s.name for s in discovered]
    assert "data-analyst" in names
    
    s = next(s for s in discovered if s.name == "data-analyst")
    assert s.is_active is True
    assert s.source == "project"


def test_skills_prompt_block():
    skills = [
        SkillDefinition(
            name="security-audit",
            description="Scans project for leaked credentials",
            tools=["grep_search"],
            instructions="Check .env and private keys.",
            is_active=True
        ),
        SkillDefinition(
            name="inactive-skill",
            description="Should not appear",
            is_active=False
        )
    ]
    prompt_block = SkillManager.build_skills_prompt_block(skills)
    assert "<skills>" in prompt_block
    assert "</skills>" in prompt_block
    assert "**security-audit**" in prompt_block
    assert "(Tools: grep_search)" in prompt_block
    assert "inactive-skill" not in prompt_block


def test_toggle_skill_state():
    SkillManager.toggle_skill_state("test-toggle-skill", False)
    assert _SKILL_STATE_OVERRIDES.get("test-toggle-skill") is False
    
    SkillManager.toggle_skill_state("test-toggle-skill", True)
    assert _SKILL_STATE_OVERRIDES.get("test-toggle-skill") is True


@pytest.mark.asyncio
async def test_skills_discovered_and_toggle_api(client: AsyncClient, temp_skills_workspace):
    # 1. Signup & Auth
    signup_payload = {
        "email": "skills.tester@carole.ai",
        "password": "supersecurepassword123"
    }
    signup_res = await client.post("/api/auth/signup", json=signup_payload)
    assert signup_res.status_code == 200, signup_res.text
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Call GET /api/skills/discovered with workspace_path
    res = await client.get(
        f"/api/skills/discovered?workspace_path={str(temp_skills_workspace)}",
        headers=headers
    )
    assert res.status_code == 200, res.text
    discovered = res.json()
    assert isinstance(discovered, list)
    names = [d["name"] for d in discovered]
    assert "data-analyst" in names

    # 3. Call POST /api/skills/toggle
    toggle_res = await client.post(
        "/api/skills/toggle",
        json={"name": "data-analyst", "is_active": False},
        headers=headers
    )
    assert toggle_res.status_code == 200, toggle_res.text
    assert toggle_res.json()["is_active"] is False

    # Check discovered again reflects inactive state
    res2 = await client.get(
        f"/api/skills/discovered?workspace_path={str(temp_skills_workspace)}",
        headers=headers
    )
    assert res2.status_code == 200
    da = next(d for d in res2.json() if d["name"] == "data-analyst")
    assert da["is_active"] is False


@pytest.mark.asyncio
async def test_skills_discovered_with_malformed_team_id(client: AsyncClient, temp_skills_workspace):
    """Verify that passing undefined, null, or invalid UUID string does not trigger a 500 error."""
    signup_payload = {
        "email": "malformed.uuid@carole.ai",
        "password": "supersecurepassword123"
    }
    signup_res = await client.post("/api/auth/signup", json=signup_payload)
    assert signup_res.status_code == 200
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    for bad_team in ["undefined", "null", "not-a-uuid", "", "123"]:
        res = await client.get(
            f"/api/skills/discovered?workspace_path={str(temp_skills_workspace)}&team_id={bad_team}",
            headers=headers
        )
        assert res.status_code == 200, f"Failed for team_id={bad_team}: {res.text}"
        assert isinstance(res.json(), list)


@pytest.mark.asyncio
async def test_observability_dag_and_code_graph_endpoints(client: AsyncClient):
    """Verify that DAG and code-graph endpoints return 200 even with bad or absent params."""
    signup_payload = {
        "email": "obs.tester@carole.ai",
        "password": "supersecurepassword123"
    }
    signup_res = await client.post("/api/auth/signup", json=signup_payload)
    assert signup_res.status_code == 200
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. DAG endpoint with and without params
    dag_res1 = await client.get("/api/observability/dag", headers=headers)
    assert dag_res1.status_code == 200
    assert "nodes" in dag_res1.json()
    assert "edges" in dag_res1.json()

    dag_res2 = await client.get("/api/observability/dag?team_id=undefined", headers=headers)
    assert dag_res2.status_code == 200

    # 2. Code Graph endpoint with and without params
    cg_res1 = await client.get("/api/observability/code-graph", headers=headers)
    assert cg_res1.status_code == 200
    assert "nodes" in cg_res1.json()
    assert "edges" in cg_res1.json()

    cg_res2 = await client.get("/api/observability/code-graph?project_id=undefined", headers=headers)
    assert cg_res2.status_code == 200


def test_save_and_delete_filesystem_skill(temp_skills_workspace):
    """Test saving a new skill package, reading its content, and deleting it."""
    # 1. Save new skill package
    content = (
        "---\n"
        "name: automated-tester\n"
        "description: Automated testing and QA runner\n"
        "tools:\n"
        "  - run_command\n"
        "author: Carole AI\n"
        "version: 1.0.0\n"
        "is_active: true\n"
        "---\n\n"
        "# Instructions\nRun pytest and inspect test failure logs.\n"
    )
    skill_def = SkillManager.save_skill_package(
        name="automated-tester",
        content=content,
        target="project",
        workspace_root=temp_skills_workspace
    )
    assert skill_def.name == "automated-tester"
    assert skill_def.description == "Automated testing and QA runner"
    assert (temp_skills_workspace / ".carole" / "skills" / "automated-tester" / "SKILL.md").exists()

    # 2. Get skill content
    info = SkillManager.get_skill_content("automated-tester", workspace_root=temp_skills_workspace)
    assert info is not None
    assert info["name"] == "automated-tester"
    assert "Run pytest" in info["content"]

    # 3. Delete skill
    deleted = SkillManager.delete_filesystem_skill("automated-tester", workspace_root=temp_skills_workspace)
    assert deleted is True
    assert not (temp_skills_workspace / ".carole" / "skills" / "automated-tester").exists()

    # Verify get_skill_content returns None after deletion
    assert SkillManager.get_skill_content("automated-tester", workspace_root=temp_skills_workspace) is None


@pytest.mark.asyncio
async def test_create_upload_and_delete_discovered_skill_api(client: AsyncClient, temp_skills_workspace):
    """Test REST API endpoints for creating, uploading, fetching content, and deleting discovered skills."""
    signup_payload = {
        "email": "skill.creator@carole.ai",
        "password": "supersecurepassword123"
    }
    signup_res = await client.post("/api/auth/signup", json=signup_payload)
    assert signup_res.status_code == 200
    token = signup_res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. POST /api/skills/discovered (create from JSON)
    create_body = {
        "name": "api-tester",
        "content": "---\nname: api-tester\ndescription: API test runner\ntools: [run_command]\n---\n# Instructions\nRun tests.",
        "target_location": "project",
        "workspace_path": str(temp_skills_workspace)
    }
    create_res = await client.post("/api/skills/discovered", json=create_body, headers=headers)
    assert create_res.status_code == 200, create_res.text
    created_skill = create_res.json()
    assert created_skill["name"] == "api-tester"
    assert (temp_skills_workspace / ".carole" / "skills" / "api-tester" / "SKILL.md").exists()

    # 2. GET /api/skills/discovered/{skill_name}/content
    content_res = await client.get(
        f"/api/skills/discovered/api-tester/content?workspace_path={str(temp_skills_workspace)}",
        headers=headers
    )
    assert content_res.status_code == 200
    assert "Run tests" in content_res.json()["content"]

    # 3. POST /api/skills/discovered/upload (upload .md file)
    md_file_content = (
        "---\n"
        "name: uploaded-linter\n"
        "description: Code linter skill\n"
        "tools:\n"
        "  - view_file\n"
        "---\n\n"
        "# Linter Rules\nCheck for stylistic issues.\n"
    ).encode("utf-8")

    upload_res = await client.post(
        "/api/skills/discovered/upload",
        data={
            "target_location": "project",
            "workspace_path": str(temp_skills_workspace),
            "skill_name": "uploaded-linter"
        },
        files={"file": ("SKILL.md", md_file_content, "text/markdown")},
        headers=headers
    )
    assert upload_res.status_code == 200, upload_res.text
    uploaded_skill = upload_res.json()
    assert uploaded_skill["name"] == "uploaded-linter"
    assert (temp_skills_workspace / ".carole" / "skills" / "uploaded-linter" / "SKILL.md").exists()

    # 4. DELETE /api/skills/discovered/{skill_name}
    del_res1 = await client.delete(
        f"/api/skills/discovered/api-tester?workspace_path={str(temp_skills_workspace)}",
        headers=headers
    )
    assert del_res1.status_code == 200
    assert del_res1.json()["deleted"] == "api-tester"
    assert not (temp_skills_workspace / ".carole" / "skills" / "api-tester").exists()

    del_res2 = await client.delete(
        f"/api/skills/discovered/uploaded-linter?workspace_path={str(temp_skills_workspace)}",
        headers=headers
    )
    assert del_res2.status_code == 200
    assert del_res2.json()["deleted"] == "uploaded-linter"
    assert not (temp_skills_workspace / ".carole" / "skills" / "uploaded-linter").exists()

