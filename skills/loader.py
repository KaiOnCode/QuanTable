"""Auto-discovers *.skill.md files and parses YAML frontmatter + Markdown body."""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Skill:
    name: str
    version: str = "1.0"
    category: str = "uncategorized"
    description: str = ""
    tools: list[str] = field(default_factory=list)
    model: str = "deepseek-chat"
    temperature: float = 0.0
    prompt_template: str = ""
    file_path: str = ""
    is_builtin: bool = True


class SkillLoader:
    """Scans a directory tree for *.skill.md files and parses them into Skill objects."""

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, Skill] = {}

    def discover(self) -> list[Skill]:
        """Scan for skills in layered order: user/, bundled/, then legacy flat files.

        User skills override bundled skills (same name = user wins).
        """
        self.skills.clear()
        seen_names: set[str] = set()

        user_dir = self.skills_dir / "user"
        bundled_dir = self.skills_dir / "bundled"

        # Layer 1: User skills (highest priority, writable)
        if user_dir.exists():
            for skill_dir in sorted(user_dir.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill = self._parse_subdir(skill_dir, is_builtin=False)
                if skill and skill.name:
                    self.skills[skill.name] = skill
                    seen_names.add(skill.name)

        # Layer 2: Bundled skills (read-only, lower priority)
        # Structure: bundled/<category>/<name>/SKILL.md
        if bundled_dir.exists():
            for cat_dir in sorted(bundled_dir.iterdir()):
                if not cat_dir.is_dir():
                    continue
                for skill_dir in sorted(cat_dir.iterdir()):
                    if not skill_dir.is_dir():
                        continue
                    if skill_dir.name in seen_names:
                        continue
                    skill = self._parse_subdir(skill_dir, is_builtin=True)
                    if skill and skill.name:
                        # Preserve the category from the directory structure
                        skill.category = cat_dir.name
                        self.skills[skill.name] = skill
                        seen_names.add(skill.name)

        # Layer 3: Legacy flat-file layout (backward compat, only if bundled is empty)
        if not seen_names:
            patterns = ["*.skill.md", "*/SKILL.md", "*.md"]
            seen_files = set()
            for pattern in patterns:
                for skill_file in sorted(self.skills_dir.rglob(pattern)):
                    if str(skill_file) in seen_files:
                        continue
                    seen_files.add(str(skill_file))
                    try:
                        skill = self._parse(skill_file)
                        if skill and skill.name:
                            self.skills[skill.name] = skill
                    except Exception:
                        pass

        return list(self.skills.values())

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self.skills.get(name)

    def _parse_subdir(self, skill_dir: Path, is_builtin: bool) -> Skill | None:
        """Parse a skill from a subdirectory containing SKILL.md."""
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            return None
        skill = self._parse(skill_file, skip_name_check=True)
        if skill:
            skill.is_builtin = is_builtin
            skill.file_path = str(skill_file)
        return skill

    def list_by_category(self, category: str) -> list[Skill]:
        """Filter skills by category."""
        return [s for s in self.skills.values() if s.category == category]

    def reload(self):
        """Re-scan and update skills dict. Use after file changes."""
        self.discover()

    def _parse(self, filepath: Path, skip_name_check: bool = False) -> Skill | None:
        """Parse a SKILL.md file. Returns None if not a valid skill."""
        # Skip non-skill files (unless forced)
        if not skip_name_check:
            skip_names = {"README", "LICENSE", "CHANGELOG", "CONTRIBUTING", "SKILL"}
            if filepath.stem in skip_names:
                return None

        raw = filepath.read_text(encoding="utf-8")
        parts = raw.split("---")

        if len(parts) < 3 or not raw.startswith("---"):
            return None  # No YAML frontmatter

        try:
            frontmatter = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return None

        name = frontmatter.get("name", "")
        if not name:
            return None  # No name = not a valid skill

        body = "---".join(parts[2:]).strip()
        if len(body) < 50:
            return None  # Too short to be useful

        return Skill(
            name=name,
            version=str(frontmatter.get("version", "1.0")),
            category=frontmatter.get("category", "uncategorized"),
            description=frontmatter.get("description", ""),
            tools=frontmatter.get("tools", []),
            model=frontmatter.get("model", "deepseek-chat"),
            temperature=float(frontmatter.get("temperature", 0.0)),
            prompt_template=body,
            file_path=str(filepath),
            is_builtin=True,
        )


# ── Singleton cache ──────────────────────────────────────────────

_loader_singleton: SkillLoader | None = None


def get_loader(skills_dir: str | None = None) -> SkillLoader:
    """Return the cached singleton SkillLoader, creating it on first call."""
    global _loader_singleton
    if _loader_singleton is None:
        from pathlib import Path as _Path
        default_dir = skills_dir or str(_Path(__file__).resolve().parent)
        _loader_singleton = SkillLoader(default_dir)
        _loader_singleton.discover()
    return _loader_singleton


def reset_loader():
    """Invalidate the singleton cache. Call after save/delete operations."""
    global _loader_singleton
    _loader_singleton = None
