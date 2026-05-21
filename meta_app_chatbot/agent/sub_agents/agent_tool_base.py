import asyncio
import json
import logging
import os
import traceback
from datetime import datetime
from typing import Annotated

import pytz
import tiktoken
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from meta_app_chatbot.agent.model_factory import ModelFactory
from meta_app_chatbot.agent.tools import odoo
from meta_app_chatbot.config.settings import settings

logger = logging.getLogger(__name__)


class BasicToolNode:
	"""A node that runs the tools requested in the last AIMessage."""

	def __init__(self, tools: list) -> None:
		self.tools_by_name = {tool.name: tool for tool in tools}

	def __call__(self, inputs: dict):
		return asyncio.run(self.call(inputs))

	async def invoke_tool(self, tool_name, tool_call):
		timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		try:
			print(
				f'[{timestamp}] INFO: Executing tool {tool_name} with args: {json.dumps(tool_call["args"], indent=2)}'
			)
			tool_result = await self.tools_by_name[tool_name].ainvoke(tool_call['args'])
			if not tool_result['success']:
				print(
					f'[{timestamp}] WARN: Tool {tool_name} failed with error: {tool_result.get("error", "Unknown error")}'
				)
				return {
					'tool_call_id': tool_call['id'],
					'name': tool_name,
					'content': f'Error: {tool_result.get("error", "Unknown error")}',
					'error': tool_result['error'],
					'args': tool_call['args'],
				}

			print(f'[{timestamp}] INFO: Tool {tool_name} executed successfully')
			return {
				'tool_call_id': tool_call['id'],
				'name': tool_name,
				'content': json.dumps(tool_result),
			}

		except Exception as e:
			print(
				f'[{timestamp}] ERROR: Critical failure in tool {tool_name}: {str(e)}'
			)
			print(
				f'[{timestamp}] DEBUG: Exception traceback:\n{traceback.format_exc()}'
			)
			return {
				'tool_call_id': tool_call['id'],
				'name': tool_name,
				'content': f'Error: {str(e)}',
				'error': str(e),
				'args': tool_call['args'],
			}

	async def call(self, inputs):
		timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		print(f'[{timestamp}] INFO: Entering tool processing node')
		if not (messages := inputs.get('messages', [])):
			print(f'[{timestamp}] ERROR: No message found in tool node input')
			raise ValueError('No message found in input')

		message = messages[-1]
		print(f'[{timestamp}] DEBUG: Processing {len(message.tool_calls)} tool calls')
		tasks = []
		for index, tool_call in enumerate(message.tool_calls):
			tool_call['args'] = {'number_of_calls': index, **tool_call['args']}
			tasks.append(self.invoke_tool(tool_call['name'], tool_call))

		results = await asyncio.gather(*tasks)

		outputs = [
			ToolMessage(
				content=result['content'],
				name=result['name'],
				tool_call_id=result['tool_call_id'],
			)
			for result in results
		]

		errors = [res for res in results if 'error' in res]

		print(
			f'[{timestamp}] INFO: Completed tool processing with {len(errors)} errors'
		)

		return {
			'messages': outputs,
			'errors_message': [err['error'] for err in errors],
			'errors_args': inputs['errors_args'] + [[err['args'] for err in errors]],
			'final_message': '\n\n'.join([res['content'] for res in results]),
			'limit_calls': inputs['limit_calls'] + 1,
		}


class AgentAsTool:
	def __init__(self, model=None, tools=[], prompt='', limit_calls=7):
		"""
		Args:
		    openaiKeys: Path to the credentials file or directly a key string.
		"""
		if model is None:
			model = settings.get('tool_agent_model') or settings.get('extra_model_type')
		print(f'[INFO] Initializing AgentAsTool with model: {model}')
		self.encoding = tiktoken.get_encoding('cl100k_base')
		# Placeholder for undefined templates
		self.agent = self.create_graph(
			ModelFactory.create_model(model_name=model, temperature=0.1), tools, prompt
		)
		self.lang = 'en'
		self.limit_calls = limit_calls
		self.fields = odoo.fields_prompt
		self.models = 'crm.lead'

	def get_token_length(self, x):
		return len(self.encoding.encode(x))

	def load_keys(self, path, key):
		"""
		Load OpenAI API keys from a JSON file.
		"""
		try:
			with open(path, encoding='utf-8') as f:
				keys = json.load(f)
			os.environ['OPENAI_API_KEY'] = keys.get(key, '')
			settings.set('OPENAI_API_KEY', keys.get(key, ''))
			print(f'[INFO] Successfully loaded keys from {path} using key {key}')
		except Exception as e:
			print('[ERROR] Exception occurred in load_keys:')
			print(traceback.format_exc())
			raise FileNotFoundError(f'Failed to load keys from {path}: {e}')

	@classmethod
	def set_city_query(cls, fields, models):
		# Set the class-level attributes
		cls.fields = fields
		cls.models = models

	def create_graph(self, model, tools, prompt):
		# print("[INFO] Creating graph for AgentAsTool Tool")
		class State(TypedDict):
			limit_calls: int = 0
			messages: Annotated[list, add_messages]
			errors_message: list = []
			errors_args: list
			final_message: str

		graph_builder = StateGraph(State)
		# print("initializing llm")
		llm = model
		# print("end llm")

		llm = llm.bind_tools(tools)
		tools_node = BasicToolNode(tools)

		def prompt_init(state: State):
			print('[DEBUG] Initializing prompt state')
			return {
				'messages': [],
				'limit_calls': 0,
				'errors_message': [],
				'errors_args': [],
			}

		def continue_search(state):
			timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
			err = state['errors_message']
			if (len(state['final_message']) == 0 or len(err) > 0) and state[
				'limit_calls'
			] < self.limit_calls:
				print(
					f'[{timestamp}] WARN: Error detected in tools. Attempt {state["limit_calls"] + 1}/{self.limit_calls}'
				)
				return 'solve_error'
			else:
				if len(err) > 0:
					print(
						f'[{timestamp}] ERROR: Maximum error correction attempts reached ({self.limit_calls})'
					)
				return END

		def solve_error(state: State):
			timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
			print(f'[{timestamp}] INFO: Error correction cycle started')
			print(
				f'[{timestamp}] DEBUG: Error details:\n'
				f'Messages: {state["errors_message"]}\n'
				f'Arguments: {state["errors_args"]}'
			)
			errors_message = state['errors_message']
			errors_args = state['errors_args']
			errors_str = '\n\n'.join(list(map(lambda x: str(x), errors_args)))
			if len(errors_message) == 0:
				errors_message = 'make another call tool the data now not avalilable'
			return {
				'messages': [
					{
						'role': 'assistant',
						'content': f"""❌ Previous call failed:
                                                    • Error message: {errors_message}
                                                    • this are Failed previous Arguments: {errors_str}
                                                    - learn from arguments and learn from it and choose the next paramters carfully and don't repeat same errors.

                                                    🔧 MANDATORY FIXES BEFORE RETRY:
                                                    1. Correct all data types (string, integer, date, etc.).
                                                    2. Ensure every required field is present and non-empty.
                                                    3. Remove or correct any invalid filter names.
                                                    4. Validate each field against the tool’s schema.
                                                    5. For dates, try alternate formats (YYYY‑MM‑DD, MM/DD/YYYY, etc.).
                                                    6. Verify logical consistency among parameters.
                                                    7. Adjust search ranges:
                                                    • Broaden date window.
                                                    • Widen price range.
                                                    • Decrease minimum bedrooms/beds .
                                                    • change range of all parmeters.
                                                    8. If permission issues persist, call with only the bare minimum fields.

                                                    🔄 RETRY STRATEGY:
                                                    - On validation errors: fix types and required values.
                                                    - On date errors: simplify or update to today’s date.
                                                    - On field-name errors: correct optional filters.
                                                    - Expand numeric and date ranges of all parmeters gradually until you get results.

                                                    ▶️ START YOUR RESPONSE with the corrected tool call using the updated parameters—do **not** just acknowledge the error.

                                                    """,
					}
				],
				'limit_calls': state['limit_calls'],
				'errors_message': [],
				'errors_args': state['errors_args'],
			}

		def chatbot(state: State):
			timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
			print(f'[{timestamp}] INFO: LLM Tool processing started ')
			try:
				messages = state['messages']
				if len(messages) > 3:
					messages = [messages[0], messages[1], messages[-2], messages[-1]]
				ans = llm.invoke(messages)
				print(f'[{timestamp}] INFO: LLM Tool processing completed successfully')
				return {'messages': [ans], 'limit_calls': state['limit_calls']}
			except Exception as e:
				print(f'[{timestamp}] ERROR: LLM Tool invocation failed: {str(e)}')
				print(
					f'[{timestamp}] DEBUG: Exception traceback:\n{traceback.format_exc()}'
				)
				raise

		graph_builder.add_node('chat', chatbot)
		graph_builder.add_node('tools', tools_node)
		graph_builder.add_node('prompt_init', prompt_init)
		graph_builder.add_edge(START, 'prompt_init')
		graph_builder.add_edge('prompt_init', 'chat')
		graph_builder.add_edge('chat', 'tools')
		graph_builder.add_conditional_edges(
			'tools', continue_search, {'solve_error': 'solve_error', END: END}
		)
		graph_builder.add_node('solve_error', solve_error)
		graph_builder.add_edge('solve_error', 'chat')
		graph = graph_builder.compile()

		def prompt_to_state(x):
			print('[DEBUG] Converting prompt to state (second lambda) Tool')
			return {'messages': x.messages, 'limit_calls': 0}

		prompt_to_state = RunnableLambda(prompt_to_state)
		graph = prompt | prompt_to_state | graph
		# print("[INFO] Graph creation complete Tool")
		return graph

	async def ask_agent(self, query, **kwargs):
		"""
		Interact with the Text-Only Agent.
		"""
		timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		try:
			italy_tz = pytz.timezone('Europe/Rome')
			italy_time = datetime.now(italy_tz)
			formatted_time = italy_time.strftime('%Y-%m-%d')

			print(f'[{timestamp}] INFO: Starting agent invocation Tool')

			print(
				f'[{timestamp}] DEBUG: Input Tool {self.name_agent} with parameters :\ntool Query: {query}\n'
			)

			res = (
				await self.agent.ainvoke(
					input={
						'query': query,
						'time': formatted_time,
						'fields': self.fields,
						'models': self.models,
						'cities': await odoo._fetch_available_cities(),
						'agent_scratchpad': [],
					}
				)
			)['final_message']

			timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
			print(f'[{timestamp}] INFO: Agent tool completed successfully')
			print(
				f'[{timestamp}] DEBUG: Final tool output:{self.get_token_length(f"{res}")} token'
			)
			return res

		except Exception as e:
			timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
			print(f'[{timestamp}] ERROR: Critical agent failure: {str(e)}')
			print(
				f'[{timestamp}] DEBUG: Exception traceback:\n{traceback.format_exc()}'
			)
			raise RuntimeError(f'Error invoking TextOnly Agent: {e}')
