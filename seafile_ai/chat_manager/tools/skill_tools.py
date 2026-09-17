from seafile_ai.chat_manager.skills import get_skill
from seafile_ai.utils.tools import BasicTool


class LoadSkill(BasicTool):
    tool = {
        'type': 'function',
        'function': {
            'name': 'load_skill',
            'description': 'Load specialized instructions and tools for an explicitly requested task.',
            'parameters': {
                'type': 'object',
                'properties': {
                    'skill': {
                        'type': 'string',
                        'enum': ['sdoc-create'],
                    },
                },
                'required': ['skill'],
            },
        },
    }

    def execute(self, skill, context, tool_executor):
        loaded_skills = tool_executor.cache.setdefault('loaded_skills', {})
        if skill in loaded_skills:
            return {'status': 'already loaded', 'skill': skill}
        loaded_skill = get_skill(skill)
        tool_executor.unregister('generate_markdown')
        loaded_skill.register_tools(tool_executor, context)
        tool_executor.cache.setdefault('skill_prompts', []).extend(loaded_skill.get_system_prompts())
        loaded_skills[skill] = loaded_skill
        return {'status': 'loaded', 'skill': skill}
