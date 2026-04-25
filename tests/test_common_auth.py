import unittest

import jwt

from common.auth import is_valid_token


class CommonAuthTest(unittest.TestCase):
    def test_is_valid_token_accepts_valid_token(self):
        token = jwt.encode({'exp': 4102444800}, 'secret', algorithm='HS256')

        self.assertTrue(is_valid_token(f'Token {token}', 'secret'))

    def test_is_valid_token_rejects_invalid_header(self):
        self.assertFalse(is_valid_token('Bearer abc', 'secret'))

    def test_is_valid_token_rejects_invalid_token(self):
        self.assertFalse(is_valid_token('Token invalid', 'secret'))


if __name__ == '__main__':
    unittest.main()
