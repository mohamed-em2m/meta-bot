import asyncio
import traceback
from dataclasses import dataclass
from typing import Any

from langchain.tools import tool

from meta_app_chatbot.agent.tools import crm_reader
from meta_app_chatbot.agent.utils import log_print
from meta_app_chatbot.config.settings import settings

from .agent_tool_base import AgentAsTool
from .tool_prompts import odoo_query_templete


@dataclass
class AgentConfig:
	"""Configuration for each agent type"""

	name: str
	description: str
	tools: list[Any]
	system_prompt_template: type(odoo_query_templete)
	retry_attempts: int = 7
	default_params: dict[str, Any] = None
	model: str = None


@dataclass
class AgentToolPair:
	"""Container for agent instance and its corresponding tool function"""

	agent: AgentAsTool
	tool: callable


class AgentToolFactory:
	"""Factory for creating standardized agent-based tools"""

	def __init__(self):
		self.agent_configs: dict[str, AgentConfig] = {}
		self.agent_pairs: dict[str, AgentToolPair] = {}

	def register_agent_type(self, agent_config: AgentConfig) -> None:
		"""Register a new agent type with its configuration"""
		self.agent_configs[agent_config.name] = agent_config

	def create_agent_tool(self, agent_type: str) -> AgentToolPair:
		"""Create both agent instance and tool function from configuration"""
		config = self.agent_configs.get(agent_type)
		if not config:
			raise ValueError(f'Unknown agent type: {agent_type}')

		# Create the prompt template
		system_template = config.system_prompt_template

		# Create the agent instance
		model = (
			config.model
			or settings.get('tool_agent_model')
			or settings.get('extra_model_type')
		)
		agent = AgentAsTool(tools=config.tools, prompt=system_template, model=model)

		# Create the tool functionkwargs
		f"""Generated tool function for {config.name}"""

		@tool
		def agent_tool(query: str = '', additions: dict = {}) -> dict:
			"""
			Execute the specialized agent tool for handling specific domain tasks.

			Args:
			    query (str):natural query to search on it's must be in normal language to search on
			    additions (optional)(str) : you shouldn't pass this this will pass automaticly
			Returns:
			    dict: A dictionary containing:
			        success (bool): Status of the request
			        data (Any): The processed result if successful
			        error (str, optional): Error message if the request fails
			        agent_type (str): The type of agent that processed the request
			        a
			Example:
			    >>> result = agent_tool(query='search hotels in Paris', lang='en')
			    >>> print(result['success'])
			    True
			"""
			try:
				log_print('info', 'start tool agent tool')

				# Merge default params with provided kwargs

				params = {'query': query, **(config.default_params or {}), **additions}
				result = asyncio.run(agent.ask_agent(**params))

				if isinstance(result, dict) and 'success' in result:
					return result
				return {'success': True, 'data': result, 'agent_type': agent_type}
			except Exception as e:
				log_print(
					'error', f'Error tool agent failed: {e} {traceback.format_exc()}'
				)

				return {'success': False, 'error': str(e), 'agent_type': agent_type}

		agent_tool.__name__ = f'{agent_type}_tool'
		agent_tool.__doc__ = config.description
		agent_tool.description = config.description
		agent_tool.name = f'{agent_type}_tool'
		agent.name_agent = f'{agent_type}_tool'
		# Create and store the pair
		pair = AgentToolPair(agent=agent, tool=agent_tool)
		self.agent_pairs[agent_type] = pair
		return pair

	def get_agent(self, agent_type: str) -> AgentAsTool | None:
		"""Get the agent instance for a specific type"""
		pair = self.agent_pairs.get(agent_type)
		return pair.agent if pair else None

	def get_tool(self, agent_type: str) -> callable | None:
		"""Get the tool function for a specific type"""
		pair = self.agent_pairs.get(agent_type)
		return pair.tool if pair else None


# Example configurations
AGENT_CONFIGS = {
	'search_apartment': AgentConfig(
		name='search_apartment',
		description="""AI Agent which is an Odoo CRM Data Agent. to search on apartments""",
		tools=[crm_reader],
		system_prompt_template=odoo_query_templete,
		model=None,
		retry_attempts=7,
	)
}


def setup_agents() -> dict[str, AgentToolPair]:
	"""
	Set up all agents and return dictionary of AgentToolPairs

	Returns:
	    Dict[str, AgentToolPair]: Dictionary mapping agent types to their
	    corresponding agent instances and tool functions
	"""
	factory = AgentToolFactory()

	# Register all agent types
	for config in AGENT_CONFIGS.values():
		factory.register_agent_type(config)

	# Create agent-tool pairs for all registered agents
	agent_pairs = {
		agent_type: factory.create_agent_tool(agent_type)
		for agent_type in AGENT_CONFIGS.keys()
	}

	return agent_pairs


agent_pairs = setup_agents()
