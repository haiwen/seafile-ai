import json
import logging
from seafile_ai import config
from seafile_ai.repo_metadata.constants import METADATA_TABLE
from seafile_ai.repo_metadata.utils import query_ai_summary_rows

logger = logging.getLogger(__name__)

SEARCH_RELEVANCE_PROMPT = """
You are a professional document relevance evaluation expert. Please determine whether documents are highly relevant to the user's search query.

## Task Description

1. First understand the **true intent** of the user's query (semantic level), not just keyword matching
2. Evaluate whether each document's summary content **substantially answers or relates to** the user's question
3. Consider file name and path as **additional semantic signals** (e.g., a file named 'financial-report.pdf' may be more relevant to finance-related queries)
4. Only return documents that are truly relevant; avoid returning irrelevant results

## User Query

{query}

## Document List

{documents_json}

## Response Format Requirements

Please return a JSON object with the following fields:
- "matches": an array containing indices of all relevant documents (starting from 0), sorted by relevance in descending order
- "scores": an object where keys are document indices and values are relevance scores (0-1, with 1 being most relevant)

Format example:
{{
    "matches": [0, 2, 5],
    "scores": {{
        "0": 0.95,
        "2": 0.82,
        "5": 0.71
    }}
}}

## Scoring Criteria

- Relevance score >= 0.7: Document content directly answers or discusses the user's question in detail
- Relevance score 0.4-0.7: Document content partially relates to the user's question and can be used as reference
- Relevance score < 0.4: Document content is basically unrelated to the user's question, do not return

## Notes

- Return only the JSON object, do not include any other text
- If no relevant documents are found, return empty matches array: {{"matches": [], "scores": {{}}}}
- Strictly sort by relevance, with the most relevant documents first
"""


class AISummarySearcher:
    def __init__(self, metadata_server_api, llm_api, batch_size=None,
                 max_documents=None, max_results=None, min_relevance_score=None):
        """
        Initialize AISummarySearcher with configurable parameters

        Args:
            metadata_server_api: MetadataServerAPI instance
            llm_api: LLMAPI instance
            batch_size: Number of documents to query per batch (default: from config)
            max_documents: Maximum total documents to query (default: from config)
            max_results: Maximum search results to return (default: from config)
            min_relevance_score: Minimum relevance score threshold (default: from config)
        """
        self.metadata_server_api = metadata_server_api
        self.llm_api = llm_api
        self.batch_size = batch_size or config.AI_SUMMARY_SEARCH_BATCH_SIZE
        self.max_documents = max_documents or config.AI_SUMMARY_SEARCH_MAX_DOCUMENTS
        self.max_results = max_results or config.AI_SUMMARY_SEARCH_MAX_RESULTS
        self.min_relevance_score = min_relevance_score or config.AI_SUMMARY_SEARCH_MIN_RELEVANCE_SCORE

    def search(self, repo_id, query, remaining_count=None, context=None):
        """
        Execute ai_summary fallback search with pagination

        Args:
            repo_id: Repository ID
            query: Search keyword/question
            remaining_count: Number of results still needed (default: from config)
            context: LLM call context (includes username, org_id, etc.)

        Returns:
            Tuple[List[dict], int, int, int, List[dict]] - (results, rows_scanned, batches_scanned, matched_count, matched_details)
        """
        context = context or {}
        if remaining_count is None:
            remaining_count = self.max_results

        logger.info('Starting ai_summary search for repo %s, query: %s, remaining: %d',
                    repo_id, query, remaining_count)

        # Perform paginated search: query documents in batches and evaluate relevance
        results = []
        rows_scanned = 0
        batches_scanned = 0
        matched_count = 0
        matched_details = []  # Store matched details for display
        offset = 0

        # Step 1: Load all documents in batches (keep batch queries to avoid large SQL)
        all_summaries = []
        while rows_scanned < self.max_documents:
            batch = self._load_ai_summaries_batch(repo_id, offset, self.batch_size)
            if not batch:
                logger.info('No more documents found, stopping search')
                break

            all_summaries.extend(batch)
            rows_scanned += len(batch)
            batches_scanned += 1
            offset += len(batch)

            logger.info('Loaded batch %d: %d documents, total scanned: %d',
                        batches_scanned, len(batch), rows_scanned)

        # Step 2: Evaluate relevance for all documents at once (full scan for global ranking)
        if all_summaries:
            logger.info('Evaluating relevance for %d documents', len(all_summaries))
            matched_indices, scores = self._evaluate_relevance(query, all_summaries, context)
            matched_count = len(matched_indices)
            
            # Collect matched details
            for idx in matched_indices:
                item = all_summaries[idx]
                matched_details.append({
                    'filepath': item['file_path'],
                    'score': scores.get(idx, 0),
                })
            
            logger.info('Found %d relevant documents, scores: %s', matched_count, scores)
            
            # Format results
            results = self._format_results(all_summaries, matched_indices, scores, repo_id)
        else:
            logger.info('No documents found for ai_summary search')

        # Sort by relevance score and truncate
        results.sort(key=lambda x: x.get('score', 0), reverse=True)
        results = results[:remaining_count]
        
        # Sort matched_details by score
        matched_details.sort(key=lambda x: x['score'], reverse=True)
        matched_details = matched_details[:remaining_count]

        logger.info('ai_summary search completed, found %d relevant documents', len(results))
        return results, rows_scanned, matched_count, matched_details

    def _load_ai_summaries_batch(self, repo_id, offset, limit):
        """
        Load a batch of ai_summary data from metadata_server with pagination

        Args:
            repo_id: Repository ID
            offset: Offset for pagination
            limit: Maximum number of documents to load

        Returns:
            List[dict] - List containing obj_id, file_name, file_path, summary, mtime, size
        """
        try:
            rows = query_ai_summary_rows(repo_id, self.metadata_server_api, offset, limit)
            logger.info('Loaded %d ai_summary rows for repo %s', len(rows), repo_id)
            summaries = []
            for row in rows:
                obj_id = row.get(METADATA_TABLE.columns.obj_id.name)
                summary = row.get(METADATA_TABLE.columns.ai_summary.name)
                parent_dir = row.get(METADATA_TABLE.columns.parent_dir.name) or ''
                file_name = row.get(METADATA_TABLE.columns.file_name.name)
                mtime = row.get(METADATA_TABLE.columns.file_mtime.name)
                size = row.get(METADATA_TABLE.columns.size.name)

                if not obj_id or not summary or not file_name:
                    continue

                # Build full file path
                if parent_dir == '/':
                    file_path = f'/{file_name}'
                else:
                    file_path = f'{parent_dir}/{file_name}'

                summaries.append({
                    'obj_id': obj_id,
                    'file_name': file_name,
                    'file_path': file_path,
                    'summary': summary,
                    'mtime': mtime,
                    'size': size,
                })
            return summaries
        except Exception as error:
            logger.error('Failed to load ai_summary batch data: %s', error)
            return []

    def _evaluate_relevance(self, query, batch_items, context):
        """
        Evaluate document relevance to query using AI

        Args:
            query: Search keyword/question
            batch_items: A batch of document data
            context: LLM call context

        Returns:
            Tuple[List[int], Dict[int, float]] - (matched indices list, relevance scores dict)
        """
        # Build data for LLM (hide obj_id, use descriptive named fields)
        documents_for_llm = []
        for idx, item in enumerate(batch_items):
            documents_for_llm.append({
                'index': idx,
                'file_name': item['file_name'],
                'file_path': item['file_path'],
                'summary': item['summary'],
            })

        documents_json = json.dumps(documents_for_llm, ensure_ascii=False, indent=2)
        prompt = SEARCH_RELEVANCE_PROMPT.format(query=query, documents_json=documents_json)

        messages = [
            {
                'role': 'system',
                'content': prompt,
            }
        ]

        try:
            response = self.llm_api.run(messages, context, json_mode=True)
            result = json.loads(response)

            matches = result.get('matches', [])
            scores = result.get('scores', {})

            # Filter results below threshold
            filtered_matches = []
            filtered_scores = {}
            for idx in matches:
                score = float(scores.get(str(idx), 0))
                if score >= self.min_relevance_score:
                    filtered_matches.append(idx)
                    filtered_scores[idx] = score

            return filtered_matches, filtered_scores

        except Exception as error:
            logger.warning('AI relevance evaluation failed: %s', error)
            return [], {}

    def _format_results(self, batch_items, matched_indices, scores, repo_id):
        """
        Format search results to match SeaSearch return format

        Args:
            batch_items: Batched document data
            matched_indices: List of matched indices
            scores: Relevance scores dictionary
            repo_id: Repository ID

        Returns:
            List[dict] - Formatted search results
        """
        results = []
        for idx in matched_indices:
            if idx < 0 or idx >= len(batch_items):
                continue

            item = batch_items[idx]
            
            # Convert mtime to float (handle string type from metadata server)
            mtime = item['mtime']
            if mtime is not None:
                try:
                    mtime = float(mtime) / 1000  # Convert ms to seconds, same as SeaSearch
                except (ValueError, TypeError):
                    mtime = 0
            else:
                mtime = 0
            
            # Convert size to int (handle string type from metadata server)
            size = item['size']
            if size is not None:
                try:
                    size = int(size)
                except (ValueError, TypeError):
                    size = 0
            else:
                size = 0
            
            result = {
                'repo_id': repo_id,
                'fullpath': item['file_path'],
                'name': item['file_name'],
                'is_dir': False,
                'score': scores.get(idx, 0),
                '_id': item['obj_id'],
                'mtime': mtime,
                'size': size,
                'content': item['summary'],
                'match_type': 'ai_summary',  # Distinguish from SeaSearch results
            }
            results.append(result)

        return results
