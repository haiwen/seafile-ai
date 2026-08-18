import logging
import time
from collections import deque

from seafile_ai import config
from seafile_ai.db.models import ChatMessages
from seafile_ai.chat_manager.memory import OpenAIMemory, build_memory_from_db
from seafile_ai.chat_manager.system_prompts import MAX_STEPS_DISABLE_TOOL_CALLS_PROMPT
from seafile_ai.chat_manager.tools import DocumentsSearch, ListFiles, MarkdownGenerator
from seafile_ai.chat_manager.utils import (
    build_chat_system_prompts,
    combine_attachments_to_message,
    get_answer_and_sources,
    strip_content_details_from_attachments,
)
from seafile_ai.chat_manager.utils.callbacker import ChatCallBacker
from seafile_ai.utils import remove_sources_content_and_snippets
from seafile_ai.utils.completion import StreamingCompletionUtils
from seafile_ai.utils.llm_api import get_llm_client_by_model_id
from seafile_ai.utils.sse import SSE
from seafile_ai.utils.tools import OpenAIToolExecutor

logger = logging.getLogger(__name__)


class BasicChat:
    def __init__(self, app):
        self.app = app
        self.search_tools = (
            DocumentsSearch(),
        )
        self.directory_tools = (
            ListFiles(),
        )
        self.content_generators = (
            MarkdownGenerator(),
        )

    def _register_tools(self, tool_executor, context):
        for tool in self.search_tools:
            tool.register(tool_executor, context=context, app=self.app)
        for tool in self.directory_tools:
            tool.register(tool_executor, context=context)
        for tool in self.content_generators:
            tool.register(tool_executor)

    def __call__(self, message, attachments, context, model):
        tool_executor = OpenAIToolExecutor()
        self._register_tools(tool_executor, context)
        return self.run(model, tool_executor, message, attachments, context=context)

    def _prepare_chat_memory(self, system_prompts, session_uuid):
        if session_uuid:
            try:
                return build_memory_from_db(
                    self.app.db_session_class,
                    system_prompts,
                    session_uuid,
                    config.CONTEXT_WINDOW_LIMIT,
                    config.CONTEXT_HISTORY_VALID_TIME,
                    ChatMessages,
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
            t_chat_start = time.time()

            llm_client = get_llm_client_by_model_id(self.app.data_logger, model)
            yield SSE.status('Preparing', 'Initializing user input')

            system_prompts = build_chat_system_prompts(context.get('repo_prompt', ''))
            memory = self._prepare_chat_memory(system_prompts, context.get('session_uuid'))

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
            t_chat_init = time.time()
            logger.info(
                '[Chat Step Analysis] Chat initialization: %.3fs, session_uuid=%s, model=%s',
                t_chat_init - t_chat_start, context.get('session_uuid'), model
            )

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
                        'stream': True,
                        'stream_options': {
                            'include_usage': True,
                        },
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

                    completion_kwargs['messages'] = memory
                    response = llm_client.completion(**completion_kwargs)
                except Exception as error:
                    time_usage = time.time() - time_begin
                    completion_retries.append(StreamingCompletionUtils.build_completion_retry_entry(
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
                current_tool_index = -1
                has_yield_answering_status = False
                recent_chunks = deque(maxlen=5)

                try:
                    for chunk in response:
                        recent_chunks.append(StreamingCompletionUtils.safe_model_dump(chunk))
                        if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                            for tool_call in chunk.tool_calls:
                                if getattr(tool_call, 'type', '') == 'function':
                                    tool_calls.append({
                                        'id': tool_call.id,
                                        'type': 'function',
                                        'function': {
                                            'name': tool_call.function.name,
                                            'arguments': tool_call.function.arguments,
                                        },
                                    })
                        elif hasattr(chunk, 'choices') and chunk.choices:
                            choice = chunk.choices[0]
                            delta = choice.delta

                            if hasattr(delta, 'tool_calls') and delta.tool_calls:
                                for tool_call_delta in delta.tool_calls:
                                    tool_call_index = tool_call_delta.index
                                    current_tool_index = StreamingCompletionUtils.ensure_tool_call_slot(
                                        tool_calls,
                                        tool_call_index,
                                        tool_call_delta.id,
                                    )
                                    if hasattr(tool_call_delta, 'function') and tool_call_delta.function:
                                        if tool_call_delta.function.name:
                                            tool_calls[current_tool_index]['function']['name'] = tool_call_delta.function.name
                                        if tool_call_delta.function.arguments:
                                            tool_calls[current_tool_index]['function']['arguments'] += tool_call_delta.function.arguments

                            if hasattr(delta, 'function_call') and delta.function_call:
                                current_tool_index = StreamingCompletionUtils.ensure_tool_call_slot(
                                    tool_calls,
                                    current_tool_index if current_tool_index >= 0 else 0,
                                )
                                if delta.function_call.name:
                                    tool_calls[current_tool_index]['function']['name'] = delta.function_call.name
                                if delta.function_call.arguments:
                                    tool_calls[current_tool_index]['function']['arguments'] += delta.function_call.arguments

                            delta_content = StreamingCompletionUtils.collect_delta_content(getattr(delta, 'content', None))
                            if delta_content:
                                if not has_yield_answering_status:
                                    yield SSE.status('Answering')
                                    has_yield_answering_status = True
                                yield SSE.answer(delta_content)
                                content += delta_content

                        if hasattr(chunk, 'usage') and chunk.usage:
                            token_usage = {
                                'input_tokens': chunk.usage.prompt_tokens,
                                'output_tokens': chunk.usage.completion_tokens,
                                'total_tokens': chunk.usage.total_tokens,
                            }
                            llm_client.logger_usage(token_usage, context)
                except Exception as error:
                    if tool_calls or content:
                        raise AssertionError('Cannot deal with invalid response')
                    time_usage = time.time() - time_begin
                    completion_retries.append(StreamingCompletionUtils.build_completion_retry_entry(
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
                    completion_retries.append(StreamingCompletionUtils.build_completion_retry_entry(
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
                        completion_retries.append(StreamingCompletionUtils.build_completion_retry_entry(
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
                    t_llm_done = time.time()
                    logger.info(
                        '[Chat Step Analysis] LLM step %d (tool call): %.3fs, tools=%s, tokens_in=%d, tokens_out=%d',
                        current_step,
                        t_llm_done - time_begin,
                        [tc['function']['name'] for tc in tool_calls],
                        token_usage.get('input_tokens', 0),
                        token_usage.get('output_tokens', 0),
                    )

                    memory.append({
                        'role': 'assistant',
                        'tool_calls': tool_calls,
                    })
                    tool_executor.thought_process.add_tool_calls_group()
                    if completion_retries:
                        tool_executor.thought_process.set_last_group_completion_retry(completion_retries)
                    tool_calls_num = len(tool_calls)
                    t_tool_start = time.time()
                    for tool_call_id, tool_call in enumerate(tool_calls):
                        yield from StreamingCompletionUtils.execute_tool_with_retry(
                            tool_executor,
                            tool_call,
                            ChatCallBacker,
                            memory,
                            tool_call_id,
                            tool_calls_num,
                        )
                    t_tool_done = time.time()
                    logger.info(
                        '[Chat Step Analysis] Tool execution (step %d): %.3fs, tools=%d',
                        current_step, t_tool_done - t_tool_start, tool_calls_num
                    )

                    tool_executor.thought_process.update_last_group_tokens_usage(token_usage)
                    tool_executor.thought_process.set_last_group_time_usage(time.time() - time_begin)
                    completion_retries = []

                    found_records = len(tool_executor.cache.get('sources_results', []))
                    if found_records:
                        yield SSE.search_found(found_records)
                    continue

                current_retry = 0
                t_llm_done = time.time()
                logger.info(
                    '[Chat Step Analysis] LLM step %d (final answer): %.3fs, answer_len=%d, tokens_in=%d, tokens_out=%d',
                    current_step,
                    t_llm_done - time_begin,
                    len(content),
                    token_usage.get('input_tokens', 0),
                    token_usage.get('output_tokens', 0),
                )

                tool_executor.thought_process.set_final_answer(
                    content,
                    current_step >= config.MAX_STEPS,
                    token_usage,
                    time.time() - time_begin,
                    retry=completion_retries if completion_retries else None,
                )
                completion_retries = []

                answer, sources = get_answer_and_sources(tool_executor, content)
                t_final = time.time()
                logger.info(
                    '[Chat Step Analysis] Chat completed: %.3fs total, steps=%d, sources=%d',
                    t_final - t_chat_start, current_step, len(sources)
                )
                yield SSE.results(answer, remove_sources_content_and_snippets(sources), tool_executor.thought_process.details)
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
