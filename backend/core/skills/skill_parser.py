"""
# backend/core/skills/skill_parser.py

Parser and validator for Antigravity & Claude Agent Skills (SKILL.md standard).
Each skill is a self-contained directory containing a SKILL.md file with
YAML frontmatter (name, description, tools, dependencies) and markdown instructions,
plus optional scripts/, references/, and examples/ folders.
"""

import os
import re
import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

logger = logging.getLogger("carole.skills.parser")

@dataclass
class SkillDefinition:
    name: str
    description: str = ""
    tools: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    is_active: bool = True
    author: str = ""
    version: str = "1.0.0"
    source: str = "project"  # "global" | "project" | "database"
    skill_dir: Optional[str] = None
    skill_file: Optional[str] = None
    instructions: str = ""
    scripts: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tools": self.tools,
            "dependencies": self.dependencies,
            "is_active": self.is_active,
            "author": self.author,
            "version": self.version,
            "source": self.source,
            "skill_dir": self.skill_dir,
            "skill_file": self.skill_file,
            "instructions": self.instructions,
            "scripts": self.scripts,
            "references": self.references,
        }


class SkillParser:
    """Parses directory-based SKILL.md files adhering to Antigravity/Claude spec."""

    @staticmethod
    def parse_skill_file(skill_path: Path, source: str = "project") -> Optional[SkillDefinition]:
        if not skill_path.exists() or not skill_path.is_file():
            return None

        try:
            content = skill_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error("Failed to read skill file '%s': %s", skill_path, e)
            return None

        skill_dir = skill_path.parent
        return SkillParser.parse_skill_content(
            content=content,
            source=source,
            skill_dir=skill_dir,
            skill_file=skill_path,
        )

    @staticmethod
    def parse_skill_content(
        content: str,
        source: str = "project",
        skill_dir: Optional[Path] = None,
        skill_file: Optional[Path] = None,
    ) -> SkillDefinition:
        """Parses raw text of a SKILL.md document into a SkillDefinition."""
        frontmatter: Dict[str, Any] = {}
        instructions = content

        # Check for YAML frontmatter between leading --- delimiters
        frontmatter_match = re.match(r"^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$", content)
        if frontmatter_match:
            raw_yaml = frontmatter_match.group(1)
            instructions = frontmatter_match.group(2).strip()
            try:
                parsed_yaml = yaml.safe_load(raw_yaml)
                if isinstance(parsed_yaml, dict):
                    frontmatter = parsed_yaml
            except Exception as yaml_err:
                logger.warning("YAML frontmatter parse error: %s", yaml_err)
                for line in raw_yaml.splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        frontmatter[k.strip()] = v.strip().strip("'\"")

        dir_name = skill_dir.name if skill_dir else "custom-skill"
        raw_name = str(frontmatter.get("name") or dir_name)
        # Sanitize to clean slug
        name = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw_name).strip("-").lower() or "custom-skill"
        description = str(frontmatter.get("description") or "")
        tools = frontmatter.get("tools") or []
        if isinstance(tools, str):
            tools = [t.strip() for t in tools.split(",") if t.strip()]

        dependencies = frontmatter.get("dependencies") or []
        if isinstance(dependencies, str):
            dependencies = [d.strip() for d in dependencies.split(",") if d.strip()]

        is_active = frontmatter.get("is_active", True)
        if isinstance(is_active, str):
            is_active = is_active.lower() not in ("false", "0", "no")

        author = str(frontmatter.get("author") or "")
        version = str(frontmatter.get("version") or "1.0.0")

        # Discover scripts and references if directory provided
        scripts = []
        references = []
        if skill_dir and skill_dir.exists() and skill_dir.is_dir():
            scripts_dir = skill_dir / "scripts"
            if scripts_dir.exists() and scripts_dir.is_dir():
                scripts = [str(f.name) for f in scripts_dir.iterdir() if f.is_file()]

            references_dir = skill_dir / "references"
            if references_dir.exists() and references_dir.is_dir():
                references = [str(f.name) for f in references_dir.iterdir() if f.is_file()]

        return SkillDefinition(
            name=name,
            description=description,
            tools=tools,
            dependencies=dependencies,
            is_active=bool(is_active),
            author=author,
            version=version,
            source=source,
            skill_dir=str(skill_dir) if skill_dir else None,
            skill_file=str(skill_file) if skill_file else (str(skill_dir / "SKILL.md") if skill_dir else None),
            instructions=instructions,
            scripts=scripts,
            references=references,
        )

    @staticmethod
    def format_skill_md(
        name: str,
        description: str,
        instructions: str,
        tools: Optional[List[str]] = None,
        author: str = "",
        version: str = "1.0.0",
        is_active: bool = True
    ) -> str:
        """Formats frontmatter and instructions into a valid standard SKILL.md."""
        frontmatter = {
            "name": name,
            "description": description,
            "tools": tools or [],
            "author": author,
            "version": version,
            "is_active": is_active,
        }
        yaml_str = yaml.dump(frontmatter, sort_keys=False).strip()
        return f"---\n{yaml_str}\n---\n\n{instructions.strip()}\n"

