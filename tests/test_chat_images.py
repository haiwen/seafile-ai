import base64
import unittest
from unittest.mock import Mock

from test_chat_memory import load_memory
from test_chat_title import load_chat_utils


class ImageAttachmentPartsTest(unittest.TestCase):
    def setUp(self):
        self.module = load_chat_utils(Mock())
        self.attachment = {
            'type': 'image',
            'repo_id': 'repo-id',
            'path': '/images/photo.png',
            'name': 'photo.png',
        }

    def assert_no_storage_access(self):
        self.module.get_repo_info.assert_not_called()
        self.module.get_file_id_by_path.assert_not_called()
        self.module.get_file_content_by_seafobj.assert_not_called()

    def test_rejects_foreign_library_before_storage_access(self):
        attachment = {**self.attachment, 'repo_id': 'foreign-repo', 'name': 1}

        self.assertEqual(self.module.build_image_content_parts([attachment], 'repo-id'), [])
        self.assert_no_storage_access()

    def test_missing_authorized_library_fails_closed(self):
        for repo_id in (None, ''):
            with self.subTest(repo_id=repo_id):
                self.assertEqual(self.module.build_image_content_parts([self.attachment], repo_id), [])
        self.assert_no_storage_access()

    def test_same_library_image_is_encoded(self):
        result = self.module.build_image_content_parts([self.attachment], 'repo-id')

        self.assertEqual(result, [{
            'type': 'image_url',
            'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(b'jpeg-image').decode()},
        }])
        self.module.get_repo_info.assert_called_once_with('repo-id')
        self.module.get_file_id_by_path.assert_called_once_with({'repo_id': 'repo-id'}, '/images/photo.png')
        self.module.get_file_content_by_seafobj.assert_called_once_with('repo-id', 'obj-id')
        self.module.resize_image_binary.assert_called_once_with(b'image-content', max_long_side=1024)

    def test_legacy_file_type_image_still_requires_same_library(self):
        attachment = {**self.attachment, 'type': 'file'}

        self.assertEqual(len(self.module.build_image_content_parts([attachment], 'repo-id')), 1)
        self.module.get_repo_info.assert_called_once_with('repo-id')


class HistoryImagePartsTest(unittest.TestCase):
    def setUp(self):
        self.module = load_memory()
        self.parts = [{'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,aW1hZ2U='}}]
        self.module.build_image_content_parts.return_value = self.parts
        self.attachment = {'repo_id': 'repo-id', 'path': '/photo.png', 'name': 'photo.png'}

    def test_restores_only_matching_user_attachments(self):
        foreign = {**self.attachment, 'repo_id': 'foreign-repo'}
        messages = [
            {'role': 'user', 'attachments': [foreign, self.attachment, None]},
            {'role': 'assistant', 'attachments': [self.attachment]},
        ]

        self.module.restore_history_image_parts(messages, 'repo-id')

        self.module.build_image_content_parts.assert_called_once_with([self.attachment], 'repo-id')
        self.assertEqual(messages[0][self.module.IMAGE_CONTENT_PARTS_KEY], self.parts)
        self.assertNotIn(self.module.IMAGE_CONTENT_PARTS_KEY, messages[1])

    def test_missing_authorized_library_does_not_restore_images(self):
        messages = [{'role': 'user', 'attachments': [self.attachment]}]

        self.module.restore_history_image_parts(messages)

        self.module.build_image_content_parts.assert_not_called()
        self.assertNotIn(self.module.IMAGE_CONTENT_PARTS_KEY, messages[0])

    def test_foreign_only_history_does_not_read_images(self):
        messages = [{'role': 'user', 'attachments': [{**self.attachment, 'repo_id': 'foreign-repo'}]}]

        self.module.restore_history_image_parts(messages, 'repo-id')

        self.module.build_image_content_parts.assert_not_called()

    def test_model_history_is_multimodal_but_thought_process_stays_text_only(self):
        self.module.combine_attachments_to_message.return_value = 'Question with attachment metadata'
        self.module.strip_content_details_from_attachments.return_value = [self.attachment]
        memory = self.module.OpenAIMemory('system')
        memory.append({
            'role': 'user', 'content': 'Question', 'created_at': 'date',
            'attachments': [self.attachment], self.module.IMAGE_CONTENT_PARTS_KEY: self.parts,
        })

        self.assertEqual(list(memory)[1]['content'], [
            {'type': 'text', 'text': 'Question with attachment metadata'}, *self.parts,
        ])
        self.assertEqual(memory.context_thought_process[0]['user_input']['message'], 'Question')
