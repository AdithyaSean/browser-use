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
				)

				return ChatInvokeCompletion(completion=response.message.content or '', usage=None)
			else:
				# Prefer strict optimized JSON schema when available, but fall back to generic JSON
				schema = SchemaOptimizer.create_optimized_json_schema(output_format)
				parse_error: Exception | None = None

				# First attempt: prompt with embedded schema (no format) to maximize compatibility
				try:
					logger.debug('Ollama structured output: primary attempt with embedded schema prompt (no format)')
					response = await self.get_client().chat(
						model=self.model,
						messages=ollama_messages,
						options=self.options,
					)
					completion_text = response.message.content or ''
					if not completion_text.strip():
						logger.warning('Ollama structured output: empty completion with embedded schema prompt')
						raise ValueError('Empty completion from model with embedded JSON schema prompt')
					# Try direct parse, else try JSON extraction
					try:
						parsed = output_format.model_validate_json(completion_text)
						logger.debug('Ollama structured output: parsed JSON directly from primary attempt')
					except Exception:
						logger.debug('Ollama structured output: direct parse failed on primary attempt, trying JSON extraction')
						maybe_json = _extract_first_json_object(completion_text)
						if not maybe_json:
							raise
						parsed = output_format.model_validate_json(maybe_json)
						logger.debug('Ollama structured output: parsed JSON via extraction from primary attempt')
					return ChatInvokeCompletion(completion=parsed, usage=None)
				except Exception as e:
					# Save and try again with a simpler JSON constraint which some models handle better
					logger.warning(f'Ollama structured output: primary attempt failed ({type(e).__name__}: {e}); falling back to format="json"')
					parse_error = e

				# Second attempt: generic JSON output (more lenient than full schema)
				logger.debug('Ollama structured output: second attempt with format="json"')
				response = await self.get_client().chat(
					model=self.model,
					messages=ollama_messages,
					format='json',
					options=self.options,
				)
				completion_text = response.message.content or ''
				if not completion_text.strip():
					# If still empty, try a free-form response and extract JSON
					logger.warning('Ollama structured output: empty completion with format="json"; trying free-form and JSON extraction')
					response_free = await self.get_client().chat(
						model=self.model,
						messages=ollama_messages,
						options=self.options,
					)
					free_text = (response_free.message.content or '').strip()
					maybe_json = _extract_first_json_object(free_text)
					if not maybe_json:
						# If we still can't get JSON, raise the original parse error for context
						logger.error('Ollama structured output: failed to extract JSON from free-form response; re-raising initial error context')
						raise parse_error
					parsed = output_format.model_validate_json(maybe_json)
					logger.debug('Ollama structured output: parsed JSON via extraction from free-form response (after format=json empty)')
					return ChatInvokeCompletion(completion=parsed, usage=None)
				# Try direct parse, else try JSON extraction
				try:
					parsed = output_format.model_validate_json(completion_text)
					logger.debug('Ollama structured output: parsed JSON directly from format="json" attempt')
				except Exception:
					logger.debug('Ollama structured output: direct parse failed on format="json" attempt, trying JSON extraction')
					maybe_json = _extract_first_json_object(completion_text)
					if not maybe_json:
						# Third attempt: free-form without format, then extract JSON
						logger.warning('Ollama structured output: JSON not found in format="json" response; trying free-form and extraction')
						response_free = await self.get_client().chat(
							model=self.model,
							messages=ollama_messages,
							options=self.options,
						)
						free_text = (response_free.message.content or '').strip()
						maybe_json = _extract_first_json_object(free_text)
						if not maybe_json:
							logger.error('Ollama structured output: failed to extract JSON from free-form response; re-raising initial error context')
							raise parse_error
					parsed = output_format.model_validate_json(maybe_json)
					logger.debug('Ollama structured output: parsed JSON via extraction from free-form response')
				return ChatInvokeCompletion(completion=parsed, usage=None)

		except Exception as e:
			raise ModelProviderError(message=str(e), model=self.name) from e
