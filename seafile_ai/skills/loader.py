from functools import lru_cache
from pathlib import Path

from .parser import SKILL_NAME_RE, parse_skill_markdown

BUILTIN_ROOT = Path(__file__).resolve().parent / 'builtin'


@lru_cache(maxsize=None)
def load_builtin_skill(name):
    if not isinstance(name, str) or not SKILL_NAME_RE.fullmatch(name):
        raise ValueError('Invalid skill name')
    return parse_skill_markdown((BUILTIN_ROOT / name / 'SKILL.md').read_text(encoding='utf-8'), name)
