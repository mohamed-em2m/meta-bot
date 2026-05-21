import asyncio
import logging
import time
import traceback
from datetime import datetime
from typing import Any

import pytz
from firebase_admin.firestore import SERVER_TIMESTAMP
from meta_app_chatbot.agent.supports import AudioController, MessageController
from meta_app_chatbot.config.settings import settings
from meta_app_chatbot.db.firestore import FirestoreFactory
from meta_app_chatbot.db.rag.big_query_rag import UnifiedBigQueryRAG
from meta_app_chatbot.voice.voice import GoogleSpeechService

from .create_graph_agent import create_graph
from .main_prompts import (
	divide_agent_prompt,
	divide_audio_prompt,
	divied_text_parser,
	facts_extractor_prompt,
	history_prompt,
	main_prompt,
	summarize_parser,
	summarize_response_prompt,
)
from .model_factory import ModelFactory
from .sub_agents import agent_pairs
from .tools import (
	create_payment_and_booking,
	delete_payment_and_booking,
	facebook,
	odoo,
	read_data_by_reveal_id,
	whatsapp,
)
from .utils import (
	create_messages_to_ai_format_v2,
	get_token_length,
	load_json,
	log_print,
)

logger = logging.getLogger(__name__)


class Agent(AudioController, MessageController):
	def __init__(
		self,
		project_id=None,
		rag_dataset=None,
		rag_table=None,
		few_shot_table=None,
		user_messages_db: str = None,
		pool_messages_db: str = None,
		few_shots_schema_path='',
		info_schema_path='',
		main_models_type='',
		extra_models_type='',
		divider_model_type='',
		extract_model_type='',
		history_length=18,
		facebook=facebook,
		whatsapp=whatsapp,
		min_tokens_to_summarize=20,
		FirestoreFactory=FirestoreFactory,
	):
		"""Initialize the Agent with LLM models and tools."""
		try:
			self.facebook = facebook
			self.whatsapp = whatsapp
			self.history_length = history_length
			self.min_tokens_to_summarize = min_tokens_to_summarize

			self.rag_dataset = rag_dataset or settings.get('RAG_DB')
			self.project_id = project_id or settings.get('PROJECT_ID')

			self.rag_table = rag_table or settings.get('RAG_TABLE')
			self.few_shot_table = few_shot_table or settings.get('FEW_SHOTS_TABLE')

			self.user_messages_db = user_messages_db or settings.get(
				'DEFUALT_USER_DB_NAME'
			)
			self.pool_messages_db = pool_messages_db or settings.get(
				'DEFUALT_MESSAGES_POOL_DB_NAME'
			)

			self.info_schema_path = info_schema_path or settings.get('INFO_SCHEMA_PATH')
			self.few_shots_schema_path = few_shots_schema_path or settings.get(
				'FEW_SHOTS_SCHEMA_PATH'
			)

			self.main_agent_type = main_models_type or settings.get('main_model_type')

			self.extra_models_type = extra_models_type or settings.get(
				'extra_model_type'
			)

			self.divider_model_type = divider_model_type or settings.get(
				'divider_model_type'
			)
			self.extract_model_type = extract_model_type or settings.get(
				'extract_model_type'
			)

			self.info_schema = load_json(self.info_schema_path)
			self.few_shots_schema = load_json(self.few_shots_schema_path)

			self.firestore_factory = FirestoreFactory
			self.sound_controller = GoogleSpeechService()
			self.rag = UnifiedBigQueryRAG(self.project_id)

			tools = [
				create_payment_and_booking,
				delete_payment_and_booking,
				read_data_by_reveal_id,
				agent_pairs['search_apartment'].tool,
			]

			self.main_agent_llm = ModelFactory.create_model(
				model_name=self.main_agent_type, temperature=0.1
			)
			self.main_agent = create_graph(
				model=self.main_agent_llm, prompt=main_prompt, tools=tools
			)

			self.pre_agent_llm = ModelFactory.create_model(
				self.extra_models_type, temperature=0.1
			)
			self.pre_agent = history_prompt | self.pre_agent_llm
			self.summarize_respond_agent = (
				summarize_response_prompt | self.pre_agent_llm
			)

			self.divider_llm = ModelFactory.create_model(
				self.divider_model_type, temperature=0.4
			)
			self.divider_agent = divide_agent_prompt | self.divider_llm
			self.post_audio_agent = divide_audio_prompt | self.divider_llm

			self.fact_extract_llm = ModelFactory.create_model(
				self.extract_model_type, temperature=0.6
			)
			self.extract_facts_agents = facts_extractor_prompt | self.fact_extract_llm

		except Exception as e:
			logger.error(f'Failed to initialize Agent: {e}')
			raise

	async def get_context(self, query, top_k=3):
		rag_chunks = await self.rag.vector_search(
			self.rag_dataset,
			self.rag_table,
			query,
			top_k=top_k,
			schema_dict=self.info_schema,
		)
		rag_chunks_list = rag_chunks['text'].to_list()
		return '\n\n'.join(rag_chunks_list)

	async def get_few_shots(self, query, top_k=3):
		shots = await self.rag.vector_search(
			self.rag_dataset,
			self.few_shot_table,
			query,
			top_k=top_k,
			schema_dict=self.few_shots_schema,
		)
		shots_list = shots['shot'].to_list()
		return '----------------\n\n'.join(shots_list)

	async def _extract_payload(self, payload: dict) -> dict:
		"""Extracts and validates data from the incoming payload."""
		data = {
			'wa_id': payload.get('wa_id'),
			'contact_name': payload.get('contact_name', ''),
			'text_body': payload.get('text_body', ''),
			'message_id': payload.get('message_id', ''),
			'timestamp': payload.get('timestamp', ''),
			'fb_sender_id': payload.get('fb_sender_id'),
			'source': payload.get('platform'),
			'url': payload.get('url', ''),
		}
		data['user_id'] = data['wa_id'] or data['fb_sender_id']

		if not data['user_id'] or not data['text_body']:
			logger.warning('Missing required fields (user_id or text_body) in payload')
			return None

		return data

	async def pre_assistant_agent_ask(
		self, text_body: str, messages: list, facts: str, concate_user_message: str
	) -> dict:
		"""Invokes the pre-agent to summarize the conversation and determine next steps."""
		try:
			italy_tz = pytz.timezone('Europe/Rome')
			formatted_time = datetime.now(italy_tz).strftime('%Y-%m-%d %H:%M')

			pre_agent_output = await self.pre_agent.ainvoke(
				{
					'user_query': text_body,
					'conversation_history': messages,  # Use a slice for the pre-agent
					'time': formatted_time,
					'facts': facts,
					'concate_user_message': concate_user_message,
				}
			)

			parser_output = await summarize_parser.ainvoke(pre_agent_output.content)
			log_print('info', f'Pre-agent output: {parser_output}')
			print(f'Pre-agent output: {parser_output}')
			return parser_output

		except Exception as e:
			logger.error(f'Error during conversation summarization: {e}')
			return None

	async def _conditionally_extract_facts(
		self, firestore_id: str, messages: list, facts: str, last_collection_length: int
	):
		"""Checks message count and triggers fact extraction if the threshold is met."""
		collection_length = self.firestore_factory.get(
			self.user_messages_db
		).get_length(firestore_id)
		if collection_length > 0 and (
			collection_length % self.history_length == 0
			or collection_length - last_collection_length >= self.history_length
		):
			logger.info(f'Triggering fact extraction for {firestore_id}')
			asyncio.create_task(
				self.extract_facts(firestore_id, messages, facts, collection_length)
			)

	async def _generate_main_response(self, chain_input: dict) -> str:
		"""Generates the primary AI response using the main chain."""
		chain_result = await self.main_agent.ainvoke(chain_input)
		output = chain_result['messages'][-1].content
		print(output)
		return output

	async def divide_response_to_messages_text(self, user_query, response, lang):
		MAX_RETRIES = 5
		ai_response, ai_response_list = '', ''

		for attempt in range(MAX_RETRIES):
			try:
				ai_response = await self.divider_agent.ainvoke(
					input={'query': user_query, 'response': response, 'lang': lang}
				)
				ai_response_list = await divied_text_parser.ainvoke(ai_response)

				break
			except Exception as e:
				logging.warning(f"""Attempt {attempt + 1}/{MAX_RETRIES} failed: {e} """)
				await asyncio.sleep(1)

		log_print(
			'info',
			'Generated AI response for user ',
			f"""{ai_response_list} query:{user_query},
                                                                                     response: {response},
                                                                                     lang :{lang}
                                                                                        """,
		)

		return ai_response_list.messages

	async def divide_response_to_messages_audio(self, user_query, response, lang):
		MAX_RETRIES = 5
		ai_response, ai_response_list = '', ''
		for attempt in range(MAX_RETRIES):
			try:
				ai_response = await self.post_audio_agent.ainvoke(
					input={'query': user_query, 'response': response, 'lang': lang}
				)
				ai_response_list = await divied_text_parser.ainvoke(ai_response)
				break
			except Exception as e:
				logging.warning(f'Attempt {attempt + 1}/{MAX_RETRIES} failed: {e}')
				await asyncio.sleep(1)

		log_print('info', 'Generated AI response for user ', ai_response_list)

		return ai_response_list.messages

	async def summarize_response(self, response):
		if get_token_length(response) > self.min_tokens_to_summarize:
			response_summariztion = (
				await self.summarize_respond_agent.ainvoke({'response': response})
			).content
		else:
			response_summariztion = response

		return response_summariztion

	async def _send_response(
		self, source: str, user_id: str, response_parts: list[str]
	):
		"""Sends the response to the user, splitting messages if necessary."""
		for part in response_parts:
			formatted_part = self.markdown_to_facebook_chat(part)
			if len(formatted_part) > 2000:
				current_message = ''
				for line in formatted_part.split('\n'):
					if len(current_message) + len(line) + 1 > 2000:
						await self._send_platform_message(
							source, user_id, current_message.strip()
						)
						current_message = ''
					current_message += line + '\n'
				if current_message.strip():
					await self._send_platform_message(
						source, user_id, current_message.strip()
					)
			else:
				await self._send_platform_message(
					source, user_id, formatted_part.strip()
				)
		log_print('info', 'All message parts have been sent.')

	async def handle_incoming_message(
		self, p_data: dict[str, Any], *, summary_history_window: int = 3
	) -> dict[str, Any] | None:
		"""
		Handles an incoming message, processes it, and returns an AI-generated response.
		"""
		if not self._is_valid_message(p_data):
			return None

		firestore_id = self.create_collection_id(p_data['user_id'], p_data['source'])

		user_document_id = self._create_unique_document_id('user')

		user_message = self._create_user_message(p_data, user_document_id)

		await self._store_user_message(firestore_id, user_document_id, user_message)

		# get context and pre agent
		context = await self._gather_conversation_context(
			firestore_id, summary_history_window
		)

		if context['summary_output'].is_trivia_question:
			asyncio.create_task(
				self._store_assistant_response(
					p_data,
					firestore_id,
					user_document_id,
					context['summary_output'].trivia_answer,
				)
			)

			asyncio.create_task(
				self._conditionally_extract_facts(
					firestore_id,
					context['ai_formatted'],
					context['facts'],
					context['last_len'],
				)
			)

			return self._create_output(
				context['summary_output'].trivia_answer,
				context['summary_output'].lang,
				firestore_id,
				user_document_id,
				context['compressed_user_message'],
			)

		# get rag and few shots
		await self._process_and_enhance_context(firestore_id, context)

		if not await self.is_this_last_message(firestore_id, user_document_id):
			return None

		chain_input = await self._prepare_chain_input(firestore_id, p_data, context)

		ai_response = await self._generate_main_response(chain_input)

		asyncio.create_task(
			self._store_assistant_response(
				p_data, firestore_id, user_document_id, ai_response
			)
		)

		asyncio.create_task(
			self._conditionally_extract_facts(
				firestore_id,
				context['ai_formatted'],
				context['facts'],
				context['last_len'],
			)
		)

		return self._create_output(
			ai_response,
			context['summary_output'].lang,
			firestore_id,
			user_document_id,
			context['compressed_user_message'],
		)

	def _is_valid_message(self, p_data: dict[str, Any]) -> bool:
		"""Validates the incoming message data."""
		if not p_data or not p_data.get('text_body'):
			logger.warning('Invalid or empty message received.')
			return False
		logger.info(
			f'Processing message from {p_data["source"]} user {p_data["user_id"]}'
		)
		return True

	def _create_unique_document_id(self, role: str) -> str:
		"""Generates a unique document ID."""
		timestamp_micros = str(int(time.time() * 1_000_000))
		return self.create_document_id(timestamp_micros, role)

	def _create_user_message(
		self, p_data: dict[str, Any], user_document_id: str
	) -> dict[str, Any]:
		"""Creates the user message dictionary."""
		return {
			'id': user_document_id,
			'user_id': p_data['user_id'],
			'role': 'user',
			'content': p_data['text_body'],
			'message_type': (
				'audio' if p_data.get('message_type') == 'audio' else 'text'
			),
			'message_id': p_data['message_id'],
			'time': SERVER_TIMESTAMP,
			'source': p_data['source'],
		}

	async def _store_user_message(
		self, firestore_id: str, user_document_id: str, user_message: dict[str, Any]
	):
		"""Stores the user message in the user and pool databases."""
		await asyncio.gather(
			self.store_messages(
				self.user_messages_db, firestore_id, user_document_id, user_message
			),
			self.store_messages(
				self.pool_messages_db, firestore_id, user_document_id, user_message
			),
		)

	async def _gather_conversation_context(
		self, firestore_id: str, summary_history_window: int
	) -> dict[str, Any]:
		"""Gathers all necessary context for processing the message."""
		firestore_id, messages, facts, last_len = await self._get_conversation_context(
			firestore_id
		)

		ai_formatted, compressed_user_message = create_messages_to_ai_format_v2(
			messages, return_last_user=True
		)
		user_message_for_concatenation = create_messages_to_ai_format_v2(
			messages, remove_role='assistant'
		)

		to_summarize = (
			ai_formatted[-summary_history_window:]
			if summary_history_window > 0
			else ai_formatted
		)
		concatenated_user_message = ''.join(
			[message['content'] for message in user_message_for_concatenation]
		)[-200:]

		summary_output = await self.pre_assistant_agent_ask(
			compressed_user_message, to_summarize, facts, concatenated_user_message
		)

		return {
			'firestore_id': firestore_id,
			'messages': messages,
			'facts': facts,
			'last_len': last_len,
			'ai_formatted': ai_formatted,
			'compressed_user_message': compressed_user_message,
			'summary_output': summary_output,
		}

	async def _process_and_enhance_context(
		self, firestore_id: str, context: dict[str, Any]
	):
		"""Extracts facts and gathers additional context."""

		rag_query = context['summary_output'].rag_query or ''
		context['rag_info'], context['few_shots'] = await asyncio.gather(
			self.get_context(context['summary_output'].rag_query),
			self.get_few_shots(rag_query + context['compressed_user_message']),
		)

	async def _prepare_chain_input(
		self, firestore_id: str, p_data: dict[str, Any], context: dict[str, Any]
	) -> dict[str, Any]:
		"""Prepares the input dictionary for the main AI chain."""
		time_now = datetime.now(pytz.timezone('Europe/Rome')).strftime('%Y-%m-%d %H:%M')
		city_list = await odoo._fetch_available_cities()
		history_slice = context['ai_formatted'][-self.history_length :]

		log_print(
			'info', f'Compressed user messages are {context["compressed_user_message"]}'
		)

		return {
			'wa_id': p_data['user_id'],
			'contact_name': p_data['contact_name'],
			'query': context['compressed_user_message'],
			'context': context['rag_info'],
			'few_shots': context['few_shots'],
			'timestamp': p_data['timestamp'],
			'source': p_data['source'],
			'long_history_facts': context['facts'],
			'city_list': city_list,
			'lang': context['summary_output'].lang,
			'time': time_now,
			'conversation_history': history_slice,
			'additions': {
				'source': p_data['source'],
				'wa_id': p_data['user_id'],
				'message_id': p_data['message_id'],
				'fb_sender_id': p_data['user_id'],
				'id': p_data['user_id'],
				'firestore_id': firestore_id,
			},
		}

	async def _store_assistant_response(
		self,
		p_data: dict[str, Any],
		firestore_id: str,
		user_document_id: str,
		ai_response: str,
	):
		"""Summarizes and stores the assistant's response."""
		summarization = await self.summarize_response(ai_response)
		assistant_document_id = self._create_unique_document_id('assistant')

		assistant_message = {
			'id': assistant_document_id,
			'parent_user_message_id': user_document_id,
			'user_id': p_data['user_id'],
			'role': 'assistant',
			'content': summarization,
			'message_type': 'text',
			'message_id': p_data['message_id'],
			'time': SERVER_TIMESTAMP,
			'source': p_data['source'],
		}
		await self.store_messages(
			self.user_messages_db,
			firestore_id,
			assistant_document_id,
			assistant_message,
		)

	def _create_output(
		self,
		response: str,
		language: str,
		collection_id: str,
		document_id: str,
		user_query: str,
	) -> dict[str, Any]:
		"""Creates the final output dictionary."""
		return {
			'response': response,
			'lang': language,
			'collection_id': collection_id,
			'document_id': document_id,
			'user_query': user_query,
		}

	async def ask(self, payload: dict) -> None:
		"""
		Processes an incoming message and generates a response by orchestrating smaller helper functions.

		Args:
		    payload (dict): Message payload containing platform-specific data.
		"""
		try:
			p_data = await self._extract_payload(payload)

			if not p_data:
				return

			main_agent_output = await self.handle_incoming_message(p_data)

			if main_agent_output is None:
				return

			response_parts = await self.divide_response_to_messages_text(
				main_agent_output['user_query'],
				main_agent_output['response'],
				main_agent_output['lang'],
			)

			if not await self.is_this_last_message(
				main_agent_output['collection_id'], main_agent_output['document_id']
			):
				return

			await self._send_response(
				p_data['source'], p_data['user_id'], response_parts
			)

			asyncio.create_task(
				self.delete_collection(
					self.pool_messages_db, main_agent_output['collection_id']
				)
			)

		except Exception as e:
			log_print(
				'error', f'Critical error in ask function: {traceback.format_exc()}'
			)
			logger.error(f'Critical error processing message: {e}')
			# Consider implementing a fallback response here

	async def ask_audio(self, payload: dict) -> None:
		"""
		Processes an incoming audio message and generates an audio response.
		"""
		try:
			p_data = await self._extract_payload(payload)

			if not p_data or not p_data.get('url'):
				logger.warning(
					'Missing required fields (user_id or url) in audio payload'
				)
				return

			# 1. Transcribe Audio using the helper
			log_print('info', f'Transcribing audio from URL: {p_data["url"]}')
			p_data['text_body'] = await self._transcribe_audio_from_url(p_data['url'])

			log_print('info', f'End Transcribed text: {p_data["text_body"]}')

			if not p_data['text_body']:
				return

			main_agent_output = await self.handle_incoming_message(p_data)

			if main_agent_output is None:
				return

			ai_final_response_content = self.prepare_text_for_tts(
				main_agent_output['response']
			)

			response_parts = await self.divide_response_to_messages_audio(
				main_agent_output['user_query'],
				ai_final_response_content,
				main_agent_output['lang'],
			)

			if not await self.is_this_last_message(
				main_agent_output['collection_id'], main_agent_output['document_id']
			):
				return

			await self.send_audio(
				response_parts,
				p_data['source'],
				p_data['user_id'],
				main_agent_output['lang'],
			)

			asyncio.create_task(
				self.delete_collection(
					self.pool_messages_db, main_agent_output['collection_id']
				)
			)

		except Exception as e:
			logger.error(f'Critical error processing message: {e}')

	async def extract_facts(
		self,
		firestore_id: str,
		messages: str = '',
		facts: str = '',
		collection_length: int = 0,
	) -> None:
		"""
		Extract and store facts from conversation reformed_qeury.

		Args:
		    firestore_id (str): Firestore document ID
		    messages (str): Conversation messages
		    facts (str): Previously extracted facts
		"""
		try:
			# Extract facts using the facts extraction model
			fact_output = await self.extract_facts_agents.ainvoke(
				{
					'conversation_history': messages,
					'last_facts': facts,
					'collection_length': collection_length,
				}
			)

			# Store extracted facts
			await self.firestore_factory.get(self.user_messages_db).store(
				'facts',
				firestore_id,
				{'facts': fact_output.content, 'updated_at': SERVER_TIMESTAMP},
			)

			log_print('info', f'Facts extracted and stored for {firestore_id}')

		except Exception as e:
			log_print('error', f'Error extracting facts: {e} {traceback.format_exc()}')
