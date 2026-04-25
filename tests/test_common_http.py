import unittest

from common.http import parse_bool


class CommonHttpTest(unittest.TestCase):
    def test_parse_bool_handles_common_true_values(self):
        self.assertTrue(parse_bool(True))
        self.assertTrue(parse_bool('true'))
        self.assertTrue(parse_bool('YES'))
        self.assertTrue(parse_bool('1'))

    def test_parse_bool_handles_common_false_values(self):
        self.assertFalse(parse_bool(False))
        self.assertFalse(parse_bool('false'))
        self.assertFalse(parse_bool('0'))
        self.assertFalse(parse_bool('off'))


if __name__ == '__main__':
    unittest.main()
