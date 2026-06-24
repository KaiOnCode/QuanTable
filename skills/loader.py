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
        """Scan for *.md files with YAML frontmatter and return parsed Skill objects."""
        self.skills.clear()
        patterns = ["*.skill.md", "*/SKILL.md", "*.md"]
        seen = set()
        for pattern in patterns:
            for skill_file in sorted(self.skills_dir.rglob(pattern)):
                if str(skill_file) in seen:
                    continue
                seen.add(str(skill_file))
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

    def list_by_category(self, category: str) -> list[Skill]:
        """Filter skills by category."""
        return [s for s in self.skills.values() if s.category == category]

    def _parse(self, filepath: Path) -> Skill | None:
        """Parse a SKILL.md file. Returns None if not a valid skill."""
        # Skip non-skill files
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
