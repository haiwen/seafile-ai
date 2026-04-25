import sys
import types
import unittest


html2text_module = types.ModuleType('html2text')


class FakeHTML2Text:
    def __init__(self, bodywidth=0):
        self.bodywidth = bodywidth

    def handle(self, html):
        return html.replace('<ol>', '').replace('</ol>', '').replace('<ul>', '').replace('</ul>', '')


html2text_module.HTML2Text = FakeHTML2Text
sys.modules.setdefault('html2text', html2text_module)

from seafile_ai.utils.sdoc2md import _handle_list_dom


class Sdoc2MdTest(unittest.TestCase):
    def test_ordered_list_renders_ol_wrapper(self):
        list_json = {
            'children': [
                {
                    'children': [
                        {
                            'type': 'paragraph',
                            'children': [{'text': 'first'}],
                        }
                    ]
                }
            ]
        }

        result = _handle_list_dom(list_json, ordered=True)

        self.assertTrue(result.startswith('<ol>'))
        self.assertIn('first', result)


if __name__ == '__main__':
    unittest.main()
