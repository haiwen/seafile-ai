import unittest
from unittest.mock import patch

import jwt

from seafile_ai.server import apis


class SDocReviewPlanBindingTest(unittest.TestCase):
    def setUp(self):
        self.secret = 'review-plan-binding-secret-at-least-32-bytes'
        self.prompt = 'Improve the document'
        self.context = {
            'snapshot_id': 'snapshot-id',
            'blocks': [{'block_id': 'block-1'}],
        }
        self.plan = {
            'brief': None,
            'chunks': [{'chunk_index': 0, 'block_ids': ['block-1']}],
        }
        self.task_id = '00000000-0000-4000-8000-000000000001'
        self.attempt_id = '00000000-0000-4000-8000-000000000002'

    def _token(self):
        return apis._encode_review_plan_token(
            self.prompt, self.context, self.plan,
            self.task_id, self.attempt_id)

    @patch.object(apis.config, 'SECRET_KEY', 'review-plan-binding-secret-at-least-32-bytes')
    def test_binding_has_no_fixed_expiry_and_matches_the_same_attempt(self):
        token = self._token()
        payload = jwt.decode(token, self.secret, algorithms=['HS256'])

        self.assertNotIn('exp', payload)
        self.assertTrue(apis._review_plan_token_matches(
            token, self.prompt, self.context,
            self.plan['brief'], self.plan['chunks'],
            self.task_id, self.attempt_id))

    @patch.object(apis.config, 'SECRET_KEY', 'review-plan-binding-secret-at-least-32-bytes')
    def test_binding_rejects_another_task_or_attempt(self):
        token = self._token()

        self.assertFalse(apis._review_plan_token_matches(
            token, self.prompt, self.context,
            self.plan['brief'], self.plan['chunks'],
            '00000000-0000-4000-8000-000000000003', self.attempt_id))
        self.assertFalse(apis._review_plan_token_matches(
            token, self.prompt, self.context,
            self.plan['brief'], self.plan['chunks'],
            self.task_id, '00000000-0000-4000-8000-000000000004'))

    @patch.object(apis.config, 'SECRET_KEY', 'review-plan-binding-secret-at-least-32-bytes')
    def test_binding_rejects_changed_plan_content(self):
        token = self._token()
        changed_chunks = [{'chunk_index': 0, 'block_ids': ['block-2']}]

        self.assertFalse(apis._review_plan_token_matches(
            token, self.prompt, self.context,
            self.plan['brief'], changed_chunks,
            self.task_id, self.attempt_id))


if __name__ == '__main__':
    unittest.main()
