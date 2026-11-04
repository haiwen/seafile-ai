import re

import yaml

from .spec import SkillSpec

SKILL_NAME_RE = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
SKILL_HEADER_SEPARATOR = '===================='


def parse_skill_markdown(content, expected_name):
    if not isinstance(content, str) or len(content.encode('utf-8')) > 128 * 1024:
        raise ValueError('Invalid skill document')
    header, separator, body = content.replace('\r\n', '\n').partition(SKILL_HEADER_SEPARATOR)
    if not separator or not body.strip():
        raise ValueError('Skill metadata and instructions are required')
    metadata = yaml.safe_load(header)
    if not isinstance(metadata, dict):
        raise ValueError('Invalid skill metadata')
    name, description = metadata.get('name'), metadata.get('description')
    if not isinstance(name, str) or not SKILL_NAME_RE.fullmatch(name) or name != expected_name or len(name) > 64:
        raise ValueError('Invalid skill name')
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError('Invalid skill description')
    return SkillSpec(name, description.strip(), body.strip())


def extract_skill_command(message, names):
    if not isinstance(message, str):
        return None, message
    match = re.match(r'^\s*/([a-z0-9]+(?:-[a-z0-9]+)*)(?=\s|$)', message)
    if match and match.group(1) in names:
        return match.group(1), message[match.end():].lstrip()
    return None, message
