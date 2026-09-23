from seafile_ai.chat_manager.skills.sdoc_create import SdocCreateSkill


SKILLS = {
    'sdoc-create': SdocCreateSkill,
}


def get_skill(name):
    skill_class = SKILLS.get(name)
    if not skill_class:
        raise ValueError('Unknown skill: %s' % name)
    return skill_class()
