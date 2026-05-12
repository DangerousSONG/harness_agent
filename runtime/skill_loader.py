# runtime/skill_loader.py

from pathlib import Path
import re


class SkillLoader:
    def __init__(self, skills_dir: Path):
        self.skills = {}

        if skills_dir.exists():
            for f in sorted(skills_dir.rglob("SKILL.md")):
                text = f.read_text(encoding="utf-8")

                match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)

                meta = {}
                body = text

                if match:
                    for line in match.group(1).strip().splitlines():
                        if ":" in line:
                            k, v = line.split(":", 1)
                            meta[k.strip()] = v.strip()

                    body = match.group(2).strip()

                name = meta.get("name", f.parent.name)

                self.skills[name] = {
                    "meta": meta,
                    "body": body,
                    "path": str(f),
                }

    def descriptions(self) -> str:
        if not self.skills:
            return "(no skills)"

        return "\n".join(
            f"  - {name}: {skill['meta'].get('description', '-')}"
            for name, skill in self.skills.items()
        )

    def load(self, name: str) -> str:
        skill = self.skills.get(name)

        if not skill:
            available = ", ".join(self.skills.keys()) or "(none)"
            return f"Error: Unknown skill '{name}'. Available: {available}"

        return f"<skill name=\"{name}\">\n{skill['body']}\n</skill>"