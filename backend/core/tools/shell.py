"""
Shell/Bash command execution tools
"""

import subprocess
import asyncio
from typing import Optional
from . import battlefield_tool


@battlefield_tool(
    name="run_command",
    description="Execute a bash/shell command and return output",
    category="shell",
    requires_confirmation=True,
    parameters={
        "command": {"type": "string", "required": True, "description": "Command to execute"},
        "timeout": {"type": "number", "required": False, "description": "Timeout in seconds (default: 30)"}
    }
)
def run_command(command: str, timeout: int = 30) -> str:
    """Execute a shell command"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        output = []
        output.append(f"✓ Command: {command}")
        output.append(f"Exit code: {result.returncode}")

        if result.stdout:
            output.append(f"\nSTDOUT:\n{result.stdout}")

        if result.stderr:
            output.append(f"\nSTDERR:\n{result.stderr}")

        return "\n".join(output)

    except subprocess.TimeoutExpired:
        return f"✗ Command timed out after {timeout} seconds: {command}"
    except Exception as e:
        return f"✗ Error executing command: {str(e)}"


@battlefield_tool(
    name="run_command_async",
    description="Execute a long-running command in the background",
    category="shell",
    requires_confirmation=True,
    parameters={
        "command": {"type": "string", "required": True, "description": "Command to execute"},
        "working_dir": {"type": "string", "required": False, "description": "Working directory"}
    }
)
async def run_command_async(command: str, working_dir: Optional[str] = None) -> str:
    """Execute a command asynchronously"""
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir
        )

        stdout, stderr = await process.communicate()

        output = []
        output.append(f"✓ Async Command: {command}")
        output.append(f"Exit code: {process.returncode}")

        if stdout:
            output.append(f"\nSTDOUT:\n{stdout.decode()}")

        if stderr:
            output.append(f"\nSTDERR:\n{stderr.decode()}")

        return "\n".join(output)

    except Exception as e:
        return f"✗ Error executing async command: {str(e)}"


@battlefield_tool(
    name="get_environment",
    description="Get environment variables",
    category="shell",
    parameters={
        "var_name": {"type": "string", "required": False, "description": "Specific variable name (returns all if omitted)"}
    }
)
def get_environment(var_name: Optional[str] = None) -> str:
    """Get environment variables"""
    import os

    if var_name:
        value = os.getenv(var_name)
        if value is None:
            return f"✗ Environment variable '{var_name}' not found"
        return f"✓ {var_name}={value}"
    else:
        env_vars = "\n".join([f"{k}={v}" for k, v in sorted(os.environ.items())])
        return f"✓ Environment variables:\n\n{env_vars}"


@battlefield_tool(
    name="check_command_exists",
    description="Check if a command/program is available in PATH",
    category="shell",
    parameters={
        "command": {"type": "string", "required": True, "description": "Command name to check"}
    }
)
def check_command_exists(command: str) -> str:
    """Check if a command exists"""
    result = subprocess.run(
        f"which {command}",
        shell=True,
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        return f"✓ {command} found at: {result.stdout.strip()}"
    else:
        return f"✗ {command} not found in PATH"
