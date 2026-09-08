"""Migrate flat skills/<category>/<name>.md files to skills/bundled/<category>/<name>/SKILL.md.

Preserves original files for backward compatibility.
"""

import shutil
from pathlib import Path


def migrate():
    skills_root = Path(__file__).resolve().parent.parent / "skills"

    # Category dirs that contain skill .md files (skip Vibe-Trading, __pycache__, etc.)
    skip = {"Vibe-Trading", "__pycache__", "bundled", "user"}
    category_dirs = [
        d for d in sorted(skills_root.iterdir()) if d.is_dir() and d.name not in skip
    ]

    # Create target directories
    bundled_dir = skills_root / "bundled"
    bundled_dir.mkdir(parents=True, exist_ok=True)
    user_dir = skills_root / "user"
    user_dir.mkdir(parents=True, exist_ok=True)

    migrated = 0
    for cat_dir in category_dirs:
        category = cat_dir.name
        for md_file in sorted(cat_dir.glob("*.md")):
            name = md_file.stem
            target_dir = bundled_dir / category / name
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / "SKILL.md"
            if not target_file.exists():
                shutil.copy2(md_file, target_file)
                print(f"  {category}/{name}.md → bundled/{category}/{name}/SKILL.md")
                migrated += 1

    print(f"\nMigrated {migrated} skills to skills/bundled/")
    print("User skills dir: skills/user/ (empty)")


if __name__ == "__main__":
    migrate()
