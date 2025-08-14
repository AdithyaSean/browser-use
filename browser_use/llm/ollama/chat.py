from dataclasses import dataclass
import logging
from typing import Any, TypeVar, overload

import httpx
from ollama import AsyncClient as OllamaAsyncClient
from pydantic import BaseModel

from browser_use.llm.base import BaseChatModel
from browser_use.llm.exceptions import ModelProviderError
from browser_use.llm.messages import BaseMessage, SystemMessage
from browser_use.llm.ollama.serializer import OllamaMessageSerializer
from browser_use.llm.schema import SchemaOptimizer
from browser_use.llm.views import ChatInvokeCompletion

T = TypeVar('T', bound=BaseModel)

logger = logging.getLogger(__name__)


@dataclass
class ChatOllama(BaseChatModel):
	"""
	A wrapper around Ollama's chat model.
	"""

	model: str

	# # Model params
	# TODO (matic): Why is this commented out?
	# temperature: float | None = None

	# Client initialization parameters
	host: str | None = None
	timeout: float | httpx.Timeout | None = None
	client_params: dict[str, Any] | None = None
	options: dict[str, Any] | None = None
	# Keep the model loaded between requests (supported by Ollama)
	keep_alive: str | int | None = None
	# Adaptive behavior: disable format="json" if it repeatedly fails/returns empty
	_format_json_fail_count: int = 0
	_disable_format_json: bool = False

	# Static
	@property
	def provider(self) -> str:
		return 'ollama'

	def _get_client_params(self) -> dict[str, Any]:
		"""Prepare client parameters dictionary."""
		return {
			'host': self.host,
			'timeout': self.timeout,
			'client_params': self.client_params,
		}

	def get_client(self) -> OllamaAsyncClient:
		"""
		Returns an OllamaAsyncClient client.
		"""
		return OllamaAsyncClient(host=self.host, timeout=self.timeout, **self.client_params or {})

	@property
	def name(self) -> str:
		return self.model

	@overload
	async def ainvoke(self, messages: list[BaseMessage], output_format: None = None) -> ChatInvokeCompletion[str]: ...

	@overload
	async def ainvoke(self, messages: list[BaseMessage], output_format: type[T]) -> ChatInvokeCompletion[T]: ...

	async def ainvoke(
		self, messages: list[BaseMessage], output_format: type[T] | None = None
	) -> ChatInvokeCompletion[T] | ChatInvokeCompletion[str]:
		# Prepare messages; when structured output is requested, inject the full schema into a system hint
		_augmented_messages = list(messages)
		schema: dict[str, Any] | None = None
		if output_format is not None:
			schema = SchemaOptimizer.create_optimized_json_schema(output_format)
			_json_only_hint = (
				'Return ONLY a valid JSON object that strictly matches the expected schema. '
				'No prose, no code fences, no prefixes or suffixes — output pure JSON.\n'
				f"<json_schema>\n{schema}\n</json_schema>"
			)
			_augmented_messages = [SystemMessage(content=_json_only_hint), *_augmented_messages]

		ollama_messages = OllamaMessageSerializer.serialize_messages(_augmented_messages)

		def _extract_first_json_object(text: str) -> str | None:
			"""Try to extract the first full JSON object from a text string.
			Returns the JSON substring if found, else None.
			"""
			if not text:
				return None
			start = None
			depth = 0
			for i, ch in enumerate(text):
				if ch == '{':
					if start is None:
						start = i
					depth += 1
				elif ch == '}':
					if start is not None:
						depth -= 1
						if depth == 0:
							return text[start : i + 1]
			return None

		try:
			if output_format is None:
				response = await self.get_client().chat(
					model=self.model,
					messages=ollama_messages,
					options=self.options,
					keep_alive=self.keep_alive,
				)

				return ChatInvokeCompletion(completion=response.message.content or '', usage=None)
			else:
				# Try JSON-formatted response first (tends to be most reliable with local Ollama)
				parse_error: Exception | None = None
				if not self._disable_format_json:
					logger.debug('Ollama structured output: primary attempt with format="json"')
					try:
						response = await self.get_client().chat(
							model=self.model,
							messages=ollama_messages,
							format='json',
							options=self.options,
							keep_alive=self.keep_alive,
						)
						completion_text = response.message.content or ''
						if not completion_text.strip():
							raise ValueError('Empty completion from model with format=json')
						try:
							parsed = output_format.model_validate_json(completion_text)
							logger.debug('Ollama structured output: parsed JSON directly from format="json" primary attempt')
						except Exception:
							logger.debug('Ollama structured output: direct parse failed on format="json" primary attempt, trying JSON extraction')
							maybe_json = _extract_first_json_object(completion_text)
							if not maybe_json:
								raise
							parsed = output_format.model_validate_json(maybe_json)
							logger.debug('Ollama structured output: parsed JSON via extraction from format="json" primary attempt')
						return ChatInvokeCompletion(completion=parsed, usage=None)
					except Exception as e1:
						self._format_json_fail_count += 1
						if self._format_json_fail_count >= 2 and not self._disable_format_json:
							self._disable_format_json = True
							logger.warning('Ollama structured output: disabling format="json" for this session after repeated failures/empty completions')
						logger.warning(
							f'Ollama structured output: format="json" attempt failed ({type(e1).__name__}: {e1}); trying free-form and JSON extraction'
						)
						parse_error = e1

				# Second attempt: free-form response without format, then extract JSON
				try:
					response_free = await self.get_client().chat(
						model=self.model,
						messages=ollama_messages,
						options=self.options,
						keep_alive=self.keep_alive,
					)
					free_text = (response_free.message.content or '').strip()
					maybe_json = _extract_first_json_object(free_text)
					if maybe_json:
						parsed = output_format.model_validate_json(maybe_json)
						logger.debug('Ollama structured output: parsed JSON via extraction from free-form response')
						return ChatInvokeCompletion(completion=parsed, usage=None)
				except Exception as e2:
					logger.warning(
						f'Ollama structured output: free-form extraction attempt failed ({type(e2).__name__}: {e2}); trying embedded schema prompt'
					)
					parse_error = parse_error or e2

				# Final attempt: prompt with embedded schema (no format)
				try:
					logger.debug('Ollama structured output: final attempt with embedded schema prompt (no format)')
					response_schema = await self.get_client().chat(
						model=self.model,
						messages=ollama_messages,
						options=self.options,
						keep_alive=self.keep_alive,
					)
					schema_text = response_schema.message.content or ''
					if not schema_text.strip():
						raise ValueError('Empty completion from model with embedded JSON schema prompt')
					try:
						parsed = output_format.model_validate_json(schema_text)
						logger.debug('Ollama structured output: parsed JSON directly from embedded schema attempt')
					except Exception:
						logger.debug('Ollama structured output: direct parse failed on schema attempt, trying JSON extraction')
						maybe_json = _extract_first_json_object(schema_text)
						if not maybe_json:
							raise (parse_error or ValueError('Failed to extract JSON from embedded schema attempt'))
						parsed = output_format.model_validate_json(maybe_json)
						logger.debug('Ollama structured output: parsed JSON via extraction from embedded schema attempt')
					return ChatInvokeCompletion(completion=parsed, usage=None)
				except Exception as e3:
					logger.error('Ollama structured output: failed all attempts; re-raising initial error context')
					raise parse_error or e3

		except Exception as e:
			raise ModelProviderError(message=str(e), model=self.name) from e
