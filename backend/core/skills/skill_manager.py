import os
import tempfile
import re
import shutil
import uuid
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.memory.models import Skill
from core.skills.skill_parser import SkillParser, SkillDefinition

logger = logging.getLogger("carole.skills.manager")

class SkillManager:
    """
    Manages CRUD operations, multi-root filesystem discovery, and prompt injection
    of dynamic skills adhering to the Antigravity / Claude SKILL.md specification.
    """

    # ── Database-backed Skills (Legacy & UI Custom CRUD) ──

    @staticmethod
    async def get_team_skills(db: AsyncSession, team_id: str, active_only: bool = True) -> List[Skill]:
        """Retrieve all skills for a given team."""
        try:
            t_uuid = uuid.UUID(str(team_id))
        except (ValueError, TypeError, AttributeError):
            return []
        stmt = select(Skill).where(Skill.team_id == t_uuid)
        if active_only:
            stmt = stmt.where(Skill.is_active == True)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_skill(db: AsyncSession, skill_id: str) -> Optional[Skill]:
        """Retrieve a single skill by ID."""
        try:
            s_uuid = uuid.UUID(str(skill_id))
        except (ValueError, TypeError, AttributeError):
            return None
        stmt = select(Skill).where(Skill.id == s_uuid)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    async def create_skill(
        db: AsyncSession,
        team_id: str,
        name: str,
        description: str = "",
        system_prompt_addendum: str = "",
        tools: List[str] = None,
        mcp_servers: List[str] = None
    ) -> Skill:
        """Create a new skill."""
        new_skill = Skill(
            team_id=uuid.UUID(team_id),
            name=name,
            description=description,
            system_prompt_addendum=system_prompt_addendum,
            tools=tools or [],
            mcp_servers=mcp_servers or [],
            is_active=True
        )
        db.add(new_skill)
        await db.commit()
        await db.refresh(new_skill)
        return new_skill

    @staticmethod
    async def update_skill(
        db: AsyncSession,
        skill_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        system_prompt_addendum: Optional[str] = None,
        tools: Optional[List[str]] = None,
        mcp_servers: Optional[List[str]] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Skill]:
        """Update an existing skill."""
        skill = await SkillManager.get_skill(db, skill_id)
        if not skill:
            return None

        if name is not None:
            skill.name = name
        if description is not None:
            skill.description = description
        if system_prompt_addendum is not None:
            skill.system_prompt_addendum = system_prompt_addendum
        if tools is not None:
            skill.tools = tools
        if mcp_servers is not None:
            skill.mcp_servers = mcp_servers
        if is_active is not None:
            skill.is_active = is_active

        await db.commit()
        await db.refresh(skill)
        return skill

    @staticmethod
    async def delete_skill(db: AsyncSession, skill_id: str) -> bool:
        """Delete a skill permanently."""
        skill = await SkillManager.get_skill(db, skill_id)
        if not skill:
            return False
        
        await db.delete(skill)
        await db.commit()
        return True

    # ── Antigravity / Claude SKILL.md Filesystem Discovery ──

    @staticmethod
    def get_discovery_roots(workspace_root: Optional[Path] = None) -> List[tuple[Path, str]]:
        """
        Returns list of (directory_path, source_type) to scan for SKILL.md packages.
        Priority:
        1. Project-level .agents/skills/
        2. Project-level .carole/skills/
        3. Global user ~/.carole/skills/
        """
        roots = []
        candidates = []
        if workspace_root:
            candidates.append(Path(workspace_root).resolve())

        # Project discovery never includes the server checkout implicitly.

        seen_roots = set()
        for w_path in candidates:
            # Carole project skills (.carole/skills/)
            p1 = w_path / ".carole" / "skills"
            if p1.exists() and p1.is_dir() and str(p1) not in seen_roots:
                roots.append((p1, "project"))
                seen_roots.add(str(p1))
            # Standard project root skills (skills/)
            p2 = w_path / "skills"
            if p2.exists() and p2.is_dir() and str(p2) not in seen_roots:
                roots.append((p2, "project"))
                seen_roots.add(str(p2))
            # Compatibility fallback
            p3 = w_path / ".agents" / "skills"
            if p3.exists() and p3.is_dir() and str(p3) not in seen_roots:
                roots.append((p3, "project"))
                seen_roots.add(str(p3))

        # Global user home (~/.carole/skills/)
        from core.config import CAROLE_HOME_DIR
        g1 = CAROLE_HOME_DIR / "skills"
        if g1.exists() and g1.is_dir() and str(g1) not in seen_roots:
            roots.append((g1, "global"))
            seen_roots.add(str(g1))

        return roots

    @classmethod
    def get_destination_root(
        cls,
        target: str = "project",
        workspace_root: Optional[Path] = None,
    ) -> Path:
        """Resolves root directory where new SKILL.md packages should be saved (.carole/skills/)."""
        if target.lower() == "global":
            from core.config import CAROLE_HOME_DIR
            dest = CAROLE_HOME_DIR / "skills"
        else:
            if target.lower() != "project":
                raise ValueError("Skill target must be project or global")
            w_path = Path(workspace_root).resolve() if workspace_root else None
            if not w_path:
                raise ValueError("A project workspace is required")
            dest = w_path / ".carole" / "skills"

        dest.mkdir(parents=True, exist_ok=True)
        return dest

    @staticmethod
    def _safe_child(root: Path, child: Path) -> Path:
        resolved_root = root.resolve()
        resolved = child.resolve()
        if resolved == resolved_root or not resolved.is_relative_to(resolved_root):
            raise ValueError("Skill path must stay inside its discovery root")
        return resolved

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        fd, temporary = tempfile.mkstemp(prefix=".skill-", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    @classmethod
    def save_skill_package(
        cls,
        name: str,
        content: str,
        target: str = "project",
        workspace_root: Optional[Path] = None,
    ) -> SkillDefinition:
        """
        Validates content and writes it to <target_root>/<skill_name>/SKILL.md.
        Hot-reloads the skill into the active catalog immediately.
        """
        clean_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", name).strip("-").lower()
        if not clean_name:
            raise ValueError("Skill name must contain at least one alphanumeric character.")
        if clean_name.upper() in {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)], *[f"LPT{i}" for i in range(1, 10)]}:
            raise ValueError("Skill name is a reserved filesystem name")

        dest_root = cls.get_destination_root(target=target, workspace_root=workspace_root)
        skill_dir = cls._safe_child(dest_root, dest_root / clean_name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = cls._safe_child(dest_root, skill_dir / "SKILL.md")

        # Ensure content has valid YAML frontmatter; if missing, format standard frontmatter
        cleaned_content = content.strip()
        if not re.match(r"^---\s*\n[\s\S]*?\n---\s*\n", cleaned_content):
            cleaned_content = f"---\nname: {clean_name}\ndescription: Custom skill {clean_name}\ntools: []\nauthor: user\nversion: 1.0.0\nis_active: true\n---\n\n{cleaned_content}\n"

        source = "global" if target.lower() == "global" else "project"
        parsed = SkillParser.parse_skill_content(cleaned_content, source=source, skill_dir=skill_dir, skill_file=skill_file)
        if not parsed:
            raise ValueError("Failed to parse saved SKILL.md file.")

        if parsed.name != clean_name:
            raise ValueError("Frontmatter name must match the skill package name")
        cls._write_atomic(skill_file, cleaned_content)
        logger.info("Saved and hot-loaded skill '%s' at %s", parsed.name, skill_file)
        return parsed

    @classmethod
    def delete_filesystem_skill(
        cls,
        skill_name: str,
        workspace_root: Optional[Path] = None,
    ) -> bool:
        """Deletes a discovered skill directory from disk."""
        clean_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", skill_name).strip("-").lower()
        if not clean_name:
            raise ValueError("Skill name cannot be empty")

        # Scan roots to find the skill directory
        roots = cls.get_discovery_roots(workspace_root)
        for root_dir, _ in roots:
            target_dir = cls._safe_child(root_dir, root_dir / clean_name)
            if target_dir.exists() and target_dir.is_dir():
                shutil.rmtree(target_dir)
                logger.info("Deleted skill directory %s", target_dir)
                # Delete only the selected package, never every namesake.
                return True

        return False

    @classmethod
    def get_skill_content(
        cls,
        skill_name: str,
        workspace_root: Optional[Path] = None,
    ) -> Optional[Dict[str, Any]]:
        """Returns the raw text content and metadata of a discovered SKILL.md file."""
        clean_name = re.sub(r"[^a-zA-Z0-9_-]+", "-", skill_name).strip("-").lower()
        roots = cls.get_discovery_roots(workspace_root)
        for root_dir, source in roots:
            target_file = cls._safe_child(root_dir, root_dir / clean_name / "SKILL.md")
            if target_file.exists() and target_file.is_file():
                try:
                    content = target_file.read_text(encoding="utf-8", errors="replace")
                    return {
                        "name": clean_name,
                        "content": content,
                        "path": str(target_file),
                        "source": source,
                    }
                except Exception as e:
                    logger.error("Failed to read skill content for %s: %s", skill_name, e)
                    return None
        return None

    @classmethod
    def discover_filesystem_skills(cls, workspace_root: Optional[Path] = None) -> List[SkillDefinition]:
        """Scans all discovery roots for SKILL.md packages."""
        skills: Dict[str, SkillDefinition] = {}
        roots = cls.get_discovery_roots(workspace_root)

        for root_dir, source in roots:
            try:
                for entry in root_dir.iterdir():
                    if entry.is_dir():
                        skill_file = cls._safe_child(root_dir, entry / "SKILL.md")
                        if skill_file.exists() and skill_file.is_file():
                            parsed = SkillParser.parse_skill_file(skill_file, source=source)
                            if parsed:
                                # Project overrides global if same name
                                if parsed.name not in skills:
                                    skills[parsed.name] = parsed
            except Exception as e:
                logger.error("Error scanning skills root '%s': %s", root_dir, e)

        return list(skills.values())

    @classmethod
    async def discover_all_skills(
        cls,
        workspace_root: Optional[Path] = None,
        team_id: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> List[SkillDefinition]:
        """
        Aggregates skills from all discovery roots:
        1. Filesystem SKILL.md packages (Global and Project)
        2. Database-backed custom skills
        """
        fs_skills = cls.discover_filesystem_skills(workspace_root)
        skills_map: Dict[str, SkillDefinition] = {s.name: s for s in fs_skills}

        # Load database skills if db and team_id provided
        if db and team_id:
            try:
                db_skills = await cls.get_team_skills(db, team_id, active_only=False)
                for ds in db_skills:
                    if ds.name not in skills_map:
                        active = ds.is_active
                        skills_map[ds.name] = SkillDefinition(
                            name=ds.name,
                            description=ds.description or "",
                            tools=ds.tools or [],
                            is_active=bool(active),
                            source="database",
                            instructions=ds.system_prompt_addendum or "",
                        )
            except Exception as e:
                logger.warning("Failed to load DB skills for team %s: %s", team_id, e)

        return list(skills_map.values())

    @classmethod
    def toggle_skill_state(cls, skill_name: str, is_active: bool, workspace_root: Optional[Path] = None) -> None:
        """Persist state on the selected package; namesakes in other roots are independent."""
        info = cls.get_skill_content(skill_name, workspace_root)
        if not info:
            raise ValueError("Skill not found")
        content = info["content"]
        match = re.match(r"^---\s*\n([\s\S]*?)\n---\s*\n([\s\S]*)$", content)
        state = "true" if is_active else "false"
        if match:
            front = re.sub(r"(?m)^is_active\s*:.*\n?", "", match.group(1))
            content = f"---\n{front.rstrip()}\nis_active: {state}\n---\n{match.group(2)}"
        else:
            content = f"---\nname: {skill_name}\nis_active: {state}\n---\n{content}"
        cls._write_atomic(Path(info["path"]), content)
        logger.info("Skill '%s' active state set to %s", skill_name, is_active)

    @staticmethod
    def build_skills_prompt_block(skills: List[SkillDefinition]) -> str:
        """
        Formats discovered active skills into an Antigravity-style XML prompt block.
        """
        active = [s for s in skills if s.is_active]
        if not active:
            return ""

        lines = ["<skills>", "Load relevant instructions with read_skill(name) before using a skill."]
        remaining = 6000 - sum(map(len, lines))
        for skill in active:
            entry = f"- {skill.name[:100]}: {skill.description[:240]}"
            if len(entry) + 1 > remaining:
                lines.append("Additional skills are available through discovery.")
                break
            lines.append(entry)
            remaining -= len(entry) + 1
        lines.append("</skills>")
        return "\n".join(lines)



# Singleton
skill_manager = SkillManager()
