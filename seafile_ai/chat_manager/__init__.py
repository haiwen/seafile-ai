import logging
import time

from seafile_ai import config
from seafile_ai.db.models import ChatMessages
from seafile_ai.chat_manager.memory import OpenAIMemory, build_memory_from_db
from seafile_ai.chat_manager.system_prompts import MAX_STEPS_DISABLE_TOOL_CALLS_PROMPT
from seafile_ai.chat_manager.tools import DocumentsSearch, ListFiles, MarkdownGenerator, ReadFiles
from seafile_ai.chat_manager.utils import (
    build_chat_system_prompts,
    combine_attachments_to_message,
    get_answer_and_sources,
    strip_content_details_from_attachments,
)
from seafile_ai.chat_manager.utils.callbacker import ChatCallBacker
from seafile_ai.chat_manager.utils.chat_utils import StreamingChatUtils
from seafile_ai.utils.llm_api import get_responses_client_by_model_id, STREAM_TEXT_DELTA, STREAM_COMPLETED
from seafile_ai.utils.sse import SSE
from seafile_ai.utils.tools import OpenAIToolExecutor

logger = logging.getLogger(__name__)


class BasicChat:
    def __init__(self, app):
        self.app = app
        self.search_tools = (
            (DocumentsSearch(),)
            if config.SEASEARCH_URL.strip() and config.SEASEARCH_TOKEN.strip()
            else ()
        )
        self.directory_tools = (
            ListFiles(),
            ReadFiles(),
        )
        self.content_generators = (
            MarkdownGenerator(),
        )

    def _register_tools(self, tool_executor, context):
        for tool in self.directory_tools:
            tool.register(tool_executor, context=context)
        for tool in self.search_tools:
            tool.register(tool_executor, context=context, app=self.app)
        for tool in self.content_generators:
            tool.register(tool_executor)

    def __call__(self, message, attachments, context, model):
        tool_executor = OpenAIToolExecutor()
        self._register_tools(tool_executor, context)
        return self.run(model, tool_executor, message, attachments, context=context)

    def _prepare_chat_memory(self, system_prompts, session_uuid, repo_id):
        if session_uuid:
            try:
                return build_memory_from_db(
                    self.app.db_session_class,
                    system_prompts,
                    session_uuid,
                    config.CONTEXT_WINDOW_LIMIT,
                    config.CONTEXT_HISTORY_VALID_TIME,
                    ChatMessages,
                    repo_id,
                )
            except Exception as error:
                logger.warning('Failure to build context: %s', error)
        return OpenAIMemory(system_prompts)

    def run(self, model, tool_executor, message, attachments, **kwargs):
        raise NotImplementedError()


class StreamingChat(BasicChat):
    def run(self, model, tool_executor, message, attachments, **kwargs):
        try:
            context = kwargs.get('context', {})

            llm_client = get_responses_client_by_model_id(self.app.data_logger, model)
            yield SSE.status('Preparing', 'Initializing user input')

            system_prompts = build_chat_system_prompts(
                context.get('repo_prompt', ''),
                documents_search_registered=bool(self.search_tools),
            )
            memory = self._prepare_chat_memory(system_prompts, context.get('session_uuid'), context.get('repo_id'))

            user_raw_message = combine_attachments_to_message(attachments, message)
            tool_executor.thought_process.set_task(
                system_prompts,
                user_raw_message,
                message,
                strip_content_details_from_attachments(attachments),
            )
            tool_executor.thought_process.context = memory.context_thought_process
            memory.append({
                'role': 'user',
                'content': user_raw_message,
            })

            current_step = 0
            current_retry = 0
            completion_retries = []
            has_inserted_max_step_prompt = False
            while current_step < config.MAX_STEPS:
                current_step += 1
                detail = f'step {current_step}'
                if current_retry:
                    detail += f', retrying {current_retry}'
                yield SSE.status('LLM Reasoning', detail)
                time_begin = time.time()
                token_usage = {}

                try:
                    completion_kwargs = {
                        'context': context,
                        'num_retries': 1,
                    }
                    if current_step < config.MAX_STEPS:
                        completion_kwargs['tools'] = tool_executor.get()
                    else:
                        if not has_inserted_max_step_prompt:
                            memory.append({
                                'role': 'system',
                                'content': MAX_STEPS_DISABLE_TOOL_CALLS_PROMPT,
                            })
                            has_inserted_max_step_prompt = True
                        completion_kwargs['tool_choice'] = 'none'

                    completion_kwargs['input'] = list(memory)
                    response = llm_client.responses_stream(**completion_kwargs)
                except Exception as error:
                    time_usage = time.time() - time_begin
                    completion_retries.append(StreamingChatUtils.build_completion_retry_entry(
                        current_step,
                        current_retry,
                        'completion_error',
                        time_usage,
                        token_usage=token_usage,
                        error=repr(error),
                    ))
                    logger.exception('Streaming completion failure at step %s: %s', current_step, error)
                    if current_retry < config.COMPLETION_MAX_RETRIES:
                        current_retry += 1
                        current_step -= 1
                        time.sleep(config.COMPLETION_RETRY_INTERVAL)
                        continue
                    tool_executor.thought_process.set_final_answer(
                        '',
                        current_step >= config.MAX_STEPS,
                        token_usage,
                        time_usage,
                        retry=completion_retries,
                    )
                    raise

                tool_calls = []
                content = ''
                result = None
                has_yield_answering_status = False

                try:
                    for kind, payload in response:
                        if kind == STREAM_TEXT_DELTA:
                            if not has_yield_answering_status:
                                yield SSE.status('Answering')
                                has_yield_answering_status = True
                            yield SSE.answer(payload)
                            content += payload
                        elif kind == STREAM_COMPLETED:
                            result = payload

                    tool_calls = result.tool_calls
                    content = result.content or content
                    token_usage = result.usage
                    if token_usage:
                        llm_client.logger_usage(token_usage, context)
                except Exception as error:
                    if tool_calls or content:
                        raise AssertionError('Cannot deal with invalid response')
                    time_usage = time.time() - time_begin
                    completion_retries.append(StreamingChatUtils.build_completion_retry_entry(
                        current_step,
                        current_retry,
                        'completion_error',
                        time_usage,
                        token_usage=token_usage,
                        error=repr(error),
                    ))
                    logger.exception('Streaming completion chunk failure at step %s: %s', current_step, error)
                    if current_retry < config.COMPLETION_MAX_RETRIES:
                        current_retry += 1
                        current_step -= 1
                        time.sleep(config.COMPLETION_RETRY_INTERVAL)
                        continue
                    tool_executor.thought_process.set_final_answer(
                        '',
                        current_step >= config.MAX_STEPS,
                        token_usage,
                        time_usage,
                        retry=completion_retries,
                    )
                    raise

                if not tool_calls and not content:
                    time_usage = time.time() - time_begin
                    completion_retries.append(StreamingChatUtils.build_completion_retry_entry(
                        current_step,
                        current_retry,
                        'empty_visible_output',
                        time_usage,
                        token_usage=token_usage,
                        error='Invalid response from LLM, at least one of keys tool_calls or content must be visible',
                    ))
                    if current_retry < config.COMPLETION_MAX_RETRIES:
                        current_retry += 1
                        current_step -= 1
                        time.sleep(config.COMPLETION_RETRY_INTERVAL)
                        continue
                    tool_executor.thought_process.set_final_answer(
                        '',
                        current_step >= config.MAX_STEPS,
                        token_usage,
                        time_usage,
                        retry=completion_retries,
                    )
                    raise AssertionError(
                        'Streaming completion returned no visible output after retries. '
                        f'step={current_step} retries={current_retry}/{config.COMPLETION_MAX_RETRIES}',
                    )

                if tool_calls:
                    if current_step >= config.MAX_STEPS:
                        time_usage = time.time() - time_begin
                        completion_retries.append(StreamingChatUtils.build_completion_retry_entry(
                            current_step,
                            current_retry,
                            'tool_calls_at_max_steps',
                            time_usage,
                            token_usage=token_usage,
                            error='Invalid response: cannot return tool_calls at max steps',
                        ))
                        if current_retry < config.COMPLETION_MAX_RETRIES:
                            current_retry += 1
                            current_step -= 1
                            time.sleep(config.COMPLETION_RETRY_INTERVAL)
                            continue
                        tool_executor.thought_process.set_final_answer(
                            '',
                            current_step >= config.MAX_STEPS,
                            token_usage,
                            time_usage,
                            retry=completion_retries,
                        )
                        raise AssertionError('Invalid response: cannot return tool_calls at max steps')

                    current_retry = 0

                    memory += result.output
                    tool_executor.thought_process.add_tool_calls_group()
                    if completion_retries:
                        tool_executor.thought_process.set_last_group_completion_retry(completion_retries)
                    tool_calls_num = len(tool_calls)
                    for tool_call_id, tool_call in enumerate(tool_calls):
                        yield from StreamingChatUtils.execute_tool_with_retry(
                            tool_executor,
                            tool_call,
                            ChatCallBacker,
                            memory,
                            tool_call_id,
                            tool_calls_num,
                        )

                    tool_executor.thought_process.update_last_group_tokens_usage(token_usage)
                    tool_executor.thought_process.set_last_group_time_usage(time.time() - time_begin)
                    completion_retries = []

                    found_records = len(tool_executor.cache.get('sources_results', []))
                    if found_records:
                        yield SSE.search_found(found_records)
                    continue

                current_retry = 0

                tool_executor.thought_process.set_final_answer(
                    content,
                    current_step >= config.MAX_STEPS,
                    token_usage,
                    time.time() - time_begin,
                    retry=completion_retries if completion_retries else None,
                )
                completion_retries = []

                answer, sources = get_answer_and_sources(tool_executor, content)
                yield SSE.results(answer, sources, tool_executor.thought_process.details)
                yield SSE.done()
                break
        except Exception as error:
            logger.exception('Streaming run AI failure: %s', error)
            try:
                yield SSE.results(
                    'There is an issue with the AI server or web server (LLM or internal server error), please try again later',
                    [],
                    tool_executor.thought_process.details,
                )
            except Exception:
                yield SSE.error(repr(error))
            yield SSE.done()
