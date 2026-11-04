import unittest

from seafile_ai.skills import SkillRegistry
from seafile_ai.skills.loader import load_builtin_skill
from seafile_ai.skills.parser import extract_skill_command, parse_skill_markdown


class BuiltinSkillTest(unittest.TestCase):
    def test_explicit_command_selects_instructions(self):
        skill, message = SkillRegistry.select('  /sdoc-create Create a plan')
        self.assertEqual(skill.name, 'sdoc-create')
        self.assertEqual(message, 'Create a plan')
        self.assertIn('<seadoc', skill.content)
        self.assertEqual(SkillRegistry.TOOL_NAMES[skill.name], ('create_sdoc',))

    def test_does_not_infer_or_inherit_authorization(self):
        for message in ('Create an SDoc', 'Example: /sdoc-create plan',
                        '````\n/sdoc-create plan\n````'):
            skill, unchanged = SkillRegistry.select(message)
            self.assertIsNone(skill)
            self.assertEqual(unchanged, message)
        SkillRegistry.select('/sdoc-create task')
        self.assertIsNone(SkillRegistry.select('Now create another one')[0])

    def test_command_requires_task(self):
        with self.assertRaises(ValueError):
            SkillRegistry.select('/sdoc-create  ')

    def test_rejects_unknown_command(self):
        with self.assertRaisesRegex(ValueError, 'Unknown skill'):
            SkillRegistry.select('/sdoc-create-other task')

    def test_skill_loader_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            load_builtin_skill('../sdoc-create')

    def test_skill_metadata_must_match_directory(self):
        with self.assertRaises(ValueError):
            parse_skill_markdown('name: wrong\ndescription: test\n====================\nBody', 'sdoc-create')

    def test_command_matches_exact_boundary(self):
        self.assertEqual(extract_skill_command('/sdoc-create\nTask', ['sdoc-create']), ('sdoc-create', 'Task'))
        self.assertEqual(extract_skill_command('/sdoc-create-more Task', ['sdoc-create']), (None, '/sdoc-create-more Task'))
