import asyncio
import json
import logging
import traceback
from datetime import datetime
from typing import Annotated, Any, TypedDict

from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from meta_app_chatbot.agent.utils import log_print

logger = logging.getLogger(__name__)


class BasicToolNode:
	"""
	A robust node that executes tools requested in the last AIMessage.

	This class handles tool execution with proper error handling, validation,
	and serialization of results.
	"""

	def __init__(self, tools: list[BaseTool]) -> None:
		"""
		Initialize the ToolNode with a list of tools.

		Args:
		    tools: List of LangChain tools to make available for execution

		Raises:
		    ValueError: If tools list is empty or contains invalid tools
		"""
		if not tools:
			raise ValueError('Tools list cannot be empty')

		self.tools_by_name = {}
		for tool in tools:
			if not hasattr(tool, 'name') or not hasattr(tool, 'invoke'):
				raise ValueError(
					f"Invalid tool: {tool}. Tools must have 'name' and 'invoke' attributes"
				)
			self.tools_by_name[tool.name] = tool

	def __call__(self, inputs: Any) -> dict[str, list[Any]]:
		"""
		Execute tools based on the last message's tool calls.

		Args:
		    inputs: Dictionary containing 'messages' key with list of messages

		Returns:
		    Dictionary with 'messages' key containing list of ToolMessage results

		Raises:
		    ValueError: If input format is invalid
		"""
		messages = inputs.get('messages', [])
		if not messages:
			raise ValueError('No messages found in input')

		last_message = messages[-1]
		if not hasattr(last_message, 'tool_calls') or not last_message.tool_calls:
			logger.warning('No tool calls found in the last message')
			return {'messages': []}

		additions = inputs.get('additions', {})

		async def async_run():
			tasks = [
				self._execute_tool_call(tool_call, additions)
				for tool_call in last_message.tool_calls
			]
			return await asyncio.gather(*tasks)

		# Create a new event loop and run the async task
		loop = asyncio.new_event_loop()
		try:
			all_outputs = loop.run_until_complete(async_run())
		finally:
			loop.close()

		return {**inputs, 'messages': all_outputs}

	async def _execute_tool_call(
		self, tool_call: Any, additions: dict | None = None
	) -> ToolMessage:
		"""
		Execute a single tool call and return the result as a ToolMessage.

		Args:
		    tool_call: Dictionary containing tool call information

		Returns:
		    ToolMessage with the tool execution result

		Raises:
		    KeyError: If required tool call fields are missing
		    ValueError: If tool is not found or arguments are invalid
		"""
		try:
			required_fields = ['name', 'args', 'id']
			for field in required_fields:
				if field not in tool_call:
					raise KeyError(f"Missing required field '{field}' in tool call")

			tool_name = tool_call['name']
			if tool_name not in self.tools_by_name:
				raise ValueError(
					f"Tool '{tool_name}' not found. Available tools: {list(self.tools_by_name.keys())}"
				)

			tool = self.tools_by_name[tool_name]
			if 'additions' in tool.args:
				tool_result = await tool.ainvoke(
					{**tool_call['args'], 'additions': additions}
				)

			else:
				tool_result = await tool.ainvoke(tool_call['args'])

			return ToolMessage(
				content=self._serialize_result(tool_result),
				name=tool_name,
				tool_call_id=tool_call['id'],
			)
		except Exception as e:
			log_print(
				'Error',
				f'Error executing tool call {tool_call.get("id", "unknown")}: {e}',
			)
			error_message = self._create_error_message(tool_call, str(e))
			return error_message

	def _create_error_message(
		self, tool_call: dict[str, Any], error: str
	) -> ToolMessage:
		"""
		Create a ToolMessage for a failed tool execution.

		Args:
		    tool_call: The original tool call that failed
		    error: Error message string

		Returns:
		    ToolMessage containing the error information
		"""
		error_content = {
			'error': error,
			'tool_name': tool_call.get('name', 'unknown'),
			'status': 'failed',
		}

		return ToolMessage(
			content=json.dumps(error_content),
			name=tool_call.get('name', 'unknown'),
			tool_call_id=tool_call.get('id', 'unknown'),
		)

	def _serialize_result(self, result: Any) -> str:
		"""
		Serialize tool result to JSON string with fallback handling.

		Args:
		    result: The result from tool execution

		Returns:
		    JSON string representation of the result
		"""
		try:
			return json.dumps(result, default=str, ensure_ascii=False)
		except (TypeError, ValueError) as e:
			logger.warning(f'Failed to serialize result as JSON: {e}')
			return str(result)

	def get_available_tools(self) -> list[str]:
		"""
		Get list of available tool names.

		Returns:
		    List of tool names that can be executed
		"""
		return list(self.tools_by_name.keys())

	def has_tool(self, tool_name: str) -> bool:
		"""
		Check if a specific tool is available.

		Args:
		    tool_name: Name of the tool to check

		Returns:
		    True if tool is available, False otherwise
		"""
		return tool_name in self.tools_by_name


def create_graph(model, tools, prompt):
	class State(TypedDict):
		# Messages have the type "list". The add_messages function
		# in the annotation defines how this state key should be updated
		# (in this case, it appends messages to the list, rather than overwriting them)
		limit_calls: int = 0
		messages: Annotated[list, add_messages]
		errors_message: list = []
		errors_args: list = []
		additions: dict = {}

	graph_builder = StateGraph(State)
	# print("initializing llm")
	llm_text = model.bind_tools(tools)
	tools_node = BasicToolNode(tools)

	def prompt_init(state: State):
		print('[DEBUG] Initializing prompt state')
		return {
			'messages': [],
			'limit_calls': 0,
			'errors_message': [],
			'errors_args': [],
		}

	def chatbot(state: State):
		timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		print(f'[{timestamp}] INFO: LLM processing started')
		try:
			ans = llm_text.invoke(state['messages'])
			# print(f"INFO: [{ans}]")
			print(f'[{timestamp}] INFO: LLM processing completed successfully')
			return {'messages': [ans], 'limit_calls': state['limit_calls']}
		except Exception as e:
			print(f'[{timestamp}] ERROR: LLM invocation failed: {str(e)}')
			print(
				f'[{timestamp}] DEBUG: Exception traceback:\n{traceback.format_exc()}'
			)
			raise

	def route_tools(
		state: State,
	):
		"""
		Use in the conditional_edge to route to the ToolNode if the last message
		has tool calls. Otherwise, route to the end.
		"""
		if isinstance(state, list):
			ai_message = state[-1]
		elif messages := state.get('messages', []):
			ai_message = messages[-1]
		else:
			raise ValueError(f'No messages found in input state to tool_edge: {state}')
		if hasattr(ai_message, 'tool_calls') and len(ai_message.tool_calls) > 0:
			return 'tools'
		return END

	graph_builder.add_node('chat', chatbot)
	graph_builder.add_node('tools', tools_node)
	graph_builder.add_node('prompt_init', prompt_init)
	graph_builder.add_edge(START, 'prompt_init')
	graph_builder.add_edge('prompt_init', 'chat')
	graph_builder.add_conditional_edges(
		'chat',
		route_tools,
		{'tools': 'tools', END: END},
	)
	graph_builder.add_edge('tools', 'chat')

	graph = graph_builder.compile()

	def prompt_to_state(x):
		print('[DEBUG] Converting prompt to state (second lambda)')
		return {
			'messages': prompt.invoke(x).messages,
			'limit_calls': 0,
			'additions': x.get('additions', {}),
		}

	prompt_to_state = RunnableLambda(prompt_to_state)
	graph = prompt_to_state | graph
	return graph
