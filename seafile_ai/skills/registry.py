import re

from .loader import load_builtin_skill
from .parser import extract_skill_command


class SkillRegistry:
    # Explicit tool policy is application code, not instructions interpreted by an LLM.
    TOOL_NAMES = {'sdoc-create': ('create_sdoc',)}

    @classmethod
    def available_skills(cls):
        return [load_builtin_skill(name) for name in cls.TOOL_NAMES]

    @classmethod
    def select(cls, message):
        name, message = extract_skill_command(message, cls.TOOL_NAMES)
        if name is None:
            if isinstance(message, str) and re.match(r'^\s*/[a-z0-9]+(?:-[a-z0-9]+)*(?=\s|$)', message):
                raise ValueError('Unknown skill command')
        if name and not message.strip():
            raise ValueError('A skill command must include a task')
        return (load_builtin_skill(name) if name else None), message

    @classmethod
    def register_tools(cls, skill, executor, context, seahub_api):
        if skill is None:
            return
        from seafile_ai.chat_manager.tools.sdoc_tools import CreateSdoc
        tools = {'create_sdoc': CreateSdoc}
        for name in cls.TOOL_NAMES[skill.name]:
            tools[name]().register(executor, context=context, seahub_api=seahub_api)
