import os
import shutil
import tempfile
import subprocess
from pathlib import Path
import pytest
from httpx import AsyncClient

from core.tools.git_tools import GitTools


@pytest.fixture
def temp_git_repo():
    temp_dir = tempfile.mkdtemp(prefix="carole_test_git_cp_")
    repo_path = Path(temp_dir)

    # Initialize a clean git repo
    subprocess.run(["git", "init"], cwd=str(repo_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Carole Test"], cwd=str(repo_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@carole.ai"], cwd=str(repo_path), check=True, capture_output=True)

    # Initial file and commit
    hello_file = repo_path / "hello.txt"
    hello_file.write_text("Hello World\n", encoding="utf-8")
    subprocess.run(["git", "add", "hello.txt"], cwd=str(repo_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True, capture_output=True)

    yield repo_path
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_git_tools_checkpoint_lifecycle(temp_git_repo):
    gt = GitTools(workspace_root=str(temp_git_repo))

    # 1. Create a checkpoint
    cp_res = await gt.create_checkpoint("First Baseline", cwd=str(temp_git_repo))
    assert cp_res["status"] == "success"
    cp_id = cp_res["checkpoint_id"]
    assert cp_id.startswith("cp_")

    # 2. List checkpoints
    checkpoints = await gt.list_checkpoints(cwd=str(temp_git_repo))
    assert len(checkpoints) >= 1
    assert any(c["checkpoint_id"] == cp_id for c in checkpoints)

    # 3. Modify existing file and create untracked file
    (temp_git_repo / "hello.txt").write_text("Modified text\n", encoding="utf-8")
    (temp_git_repo / "untracked.py").write_text("print('test')", encoding="utf-8")

    # 4. Check diff before rollback
    # First commit current changes to test diff against checkpoint
    await gt.add("-A", cwd=str(temp_git_repo))
    await gt.commit("Feature in progress", cwd=str(temp_git_repo))

    diff_res = await gt.diff_checkpoint(cp_id, cwd=str(temp_git_repo))
    assert diff_res["status"] == "success"
    file_names = [f["file"] for f in diff_res["files"]]
    assert "hello.txt" in file_names
    assert "untracked.py" in file_names

    # 5. Rollback to checkpoint
    rb_res = await gt.rollback_checkpoint(cp_id, cwd=str(temp_git_repo))
    assert rb_res["status"] == "success"

    # Verify content restored
    assert (temp_git_repo / "hello.txt").read_text(encoding="utf-8") == "Hello World\n"
    assert not (temp_git_repo / "untracked.py").exists()
