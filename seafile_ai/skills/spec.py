from dataclasses import dataclass


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    content: str
