"""Exercise the shared DOCX entry point without application/service bootstrap."""

import ast
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from zipfile import ZipFile, ZIP_DEFLATED


class DocxLimitsTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'seafile_ai/utils/__init__.py'
        tree = ast.parse(source.read_text())
        nodes = [node for node in tree.body
                 if isinstance(node, (ast.FunctionDef, ast.ClassDef))
                 and node.name in ('docx2md', 'FileSizeLimitExceeded')]
        self.mammoth = Mock()
        self.mammoth.convert_to_markdown.return_value = SimpleNamespace(value='Hello\\ world')
        self.scope = dict(BytesIO=BytesIO, ZipFile=ZipFile, mammoth=self.mammoth,
                          DOCX_MAX_MEMBER_SIZE=64, DOCX_MAX_UNCOMPRESSED_SIZE=128)
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), self.scope)

    def archive(self, sizes):
        output = BytesIO()
        with ZipFile(output, 'w', compression=ZIP_DEFLATED) as archive:
            for index, size in enumerate(sizes):
                archive.writestr('part-%s.xml' % index, b' ' * size)
        return output.getvalue()

    def test_allowed_document_preserves_conversion_behavior(self):
        content = self.archive([64, 64])
        self.assertEqual(self.scope['docx2md'](content), 'Hello world')
        args, kwargs = self.mammoth.convert_to_markdown.call_args
        self.assertEqual(args[0].getvalue(), content)
        self.assertEqual(kwargs['convert_image'](None), [])

    def test_member_and_total_limits_reject_before_parsing(self):
        for sizes in ([65], [64, 64, 1]):
            with self.subTest(sizes=sizes):
                content = self.archive(sizes)
                with patch.object(ZipFile, 'open', side_effect=AssertionError('Must not decompress')):
                    with self.assertRaises(self.scope['FileSizeLimitExceeded']):
                        self.scope['docx2md'](content)
                self.mammoth.convert_to_markdown.assert_not_called()


if __name__ == '__main__':
    unittest.main()
