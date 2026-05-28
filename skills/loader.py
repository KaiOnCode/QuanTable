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
        """Scan for *.skill.md files and return parsed Skill objects."""
        self.skills.clear()
        for skill_file in sorted(self.skills_dir.rglob("*.skill.md")):
            skill = self._parse(skill_file)
            self.skills[skill.name] = skill
        return list(self.skills.values())

    def get(self, name: str) -> Skill | None:
        """Get a skill by name."""
        return self.skills.get(name)

    def list_by_category(self, category: str) -> list[Skill]:
        """Filter skills by category."""
        return [s for s in self.skills.values() if s.category == category]

    def _parse(self, filepath: Path) -> Skill:
        """Parse a single SKILL.md file: YAML frontmatter between --- fences, then Markdown body."""
        raw = filepath.read_text(encoding="utf-8")
        parts = raw.split("---")

        frontmatter: dict = {}
        body = raw

        if len(parts) >= 3 and raw.startswith("---"):
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                pass
            body = "---".join(parts[2:]).strip()

        return Skill(
            name=frontmatter.get("name", filepath.stem.replace(".skill", "")),
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
