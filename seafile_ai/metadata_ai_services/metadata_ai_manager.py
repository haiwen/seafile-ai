import os
import logging

from gevent.pool import Pool

from seafile_ai.utils.metadata_server_api import MetadataServerAPI
from seafile_ai.metadata_ai_services.utils import METADATA_TABLE
from seafile_ai.utils.sdoc2md import sdoc2md
from seafile_ai.utils.constants import LLM_INPUT_CHARACTERS_LIMIT
from seafile_ai.utils import get_file_by_token


logger = logging.getLogger(__name__)


class MetadataAIManager:
    def __init__(self, app, llm_type):
        self.app = app
        self.llm_type = llm_type

    def update_docs_summary(self, repo_id, files_info_list):
        sql = f'SELECT `{METADATA_TABLE.columns.id.name}`, `{METADATA_TABLE.columns.parent_dir.name}`, `{METADATA_TABLE.columns.file_name.name}`, `{METADATA_TABLE.columns.obj_id.name}` FROM `{METADATA_TABLE.name}` WHERE'
        parameters = []
        fp_token_map = {}
        query_result = []
        for file_info in files_info_list:

            file_path = file_info.get('file_path')
            file_name = os.path.basename(file_path)
            _, file_ext = os.path.splitext(file_name)
            if file_ext == '.sdoc':
                parent_dir = os.path.dirname(file_path)
                sql += f' (`{METADATA_TABLE.columns.parent_dir.name}` = ? AND `{METADATA_TABLE.columns.file_name.name}` = ?) OR'
                parameters.append(parent_dir)
                parameters.append(file_name)
                fp_token_map[file_path] = file_info.get('download_token')

        sql = sql.rstrip(' OR')
        if parameters:
            query_result = self.app.metadata_server_api.query_rows(repo_id, sql, parameters).get('results', [])
        if not query_result:
            return []

        updated_summary_rows = []

        def process_row(row):
            parent_dir = row[METADATA_TABLE.columns.parent_dir.name]
            file_name = row[METADATA_TABLE.columns.file_name.name]
            path = os.path.join(parent_dir, file_name)

            row_id = row[METADATA_TABLE.columns.id.name]
            obj_id = row[METADATA_TABLE.columns.obj_id.name]

            download_token = fp_token_map[path]
            sdoc_content = get_file_by_token(download_token, file_name)
            md_content = sdoc2md(sdoc_content)[0:LLM_INPUT_CHARACTERS_LIMIT]
            summary_text = self._gen_doc_summary(md_content)
            if summary_text in ['None', 'none', None]:
                return {
                    "row_id": row_id,
                    "summary_text": '',
                    "obj_id": obj_id,
                }

            return {
                "row_id": row_id,
                "summary_text": summary_text,
                "obj_id": obj_id,
            }

        pool = Pool(10)
        rows_info = pool.map(process_row, query_result)
        pool.join()

        for row_info in rows_info:
            if row_info:
                updated_row = {
                    METADATA_TABLE.columns.id.name: row_info["row_id"],
                    METADATA_TABLE.columns.summary.name: row_info["summary_text"],
                    METADATA_TABLE.columns.obj_id.name: row_info["obj_id"]
                }
                updated_summary_rows.append(updated_row)

        if updated_summary_rows:
            self.app.metadata_server_api.update_rows(repo_id, METADATA_TABLE.id, updated_summary_rows)

        return updated_summary_rows

    def _gen_doc_summary(self, content):
        if self.llm_type == 'open-ai-proxy':
            system_content = 'You are a document summarization expert. I need you to generate a concise summary of a document that is no longer than 40 words. The summary should capture the main points and themes of the document clearly and effectively.The output language is the same as the input language. If it seems there is no content provided for summarization, just output word: None'
            system_prompt = {"role": "system", "content": system_content}
            user_prompt = {"role": "user", "content": content}
            messages = [system_prompt, user_prompt]
            summary = self.app.openai_api.chat_completions(messages)
            return summary
        else:
            logger.error('llm_type is not set correctly in config')
            return None
