import logging
from abc import ABC, abstractmethod
from typing import Any

import google.generativeai as genai
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import AzureChatOpenAI, ChatOpenAI

from meta_app_chatbot.config.settings import settings

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
# Configure Gemini
genai.configure(api_key=settings.get('VERTX_API_TOKEN'))


# Dummy classes (you can replace these with actual imports)


# ===== Abstract Base Model =====
class Model(ABC):
	@staticmethod
	@abstractmethod
	def create_model(
		model_name: str = 'gpt-mini-4.1',
		temperature: float = 0.6,
		top_p: float = 0.6,
		top_k: int = 30,
		max_retries: int = 3,
		**kwargs,
	) -> Any:
		pass


# ===== Concrete Implementations =====
class AzureModel(Model):
	@staticmethod
	def create_model(
		model_name: str = 'gpt-mini-4.1',
		temperature: float = 0.6,
		top_p: float = 0.6,
		top_k: int = 30,
		max_retries: int = 3,
		**kwargs,
	) -> AzureChatOpenAI:
		try:
			return AzureChatOpenAI(
				azure_deployment=model_name,
				temperature=temperature,
				top_p=top_p,
				max_retries=max_retries,
				openai_api_key=settings.get('AZURE_KEY'),
				azure_endpoint=settings.get('AZURE_ENDPOINT'),
				api_version=settings.get('AZURE_API_VERSION'),
				**kwargs,
			)
		except Exception as e:
			raise OSError(
				f'Missing required Azure environment variable or configuration: {e}'
			)


class GeminiModel(Model):
	@staticmethod
	def create_model(
		model_name: str = 'gemini-2.0-flash',
		temperature: float = 0.6,
		top_p: float = 0.6,
		max_retries: int = 3,
		thinking_budget: int = 100,
		**kwargs,
	) -> ChatGoogleGenerativeAI:
		try:
			return ChatGoogleGenerativeAI(
				model=model_name,
				api_key=settings.get('GEMINI_API_KEY'),
				base_url=settings.get('BASE_URL'),
				temperature=temperature,
				top_p=top_p,
				thinking_budget=thinking_budget,
				**kwargs,
			)
		except Exception as e:
			raise OSError(
				f'Missing required Google environment variable or configuration: {e}'
			)


class GptModel(Model):
	@staticmethod
	def create_model(
		model_name: str = 'gpt-4.1-mini-2025-04-14',
		temperature: float = 0.6,
		top_p: float = 0.6,
		top_k: int = 30,
		max_retries: int = 3,
		**kwargs,
	) -> ChatOpenAI:
		try:
			return ChatOpenAI(
				model=model_name,
				max_retries=max_retries,
				api_key=settings.get('OPENAI_API_KEY'),
			)
		except Exception as e:
			raise OSError(
				f'Missing required OpenAI environment variable or configuration: {e}'
			)


# ===== Factory Class with Registry =====
class ModelFactory:
	_registry: dict[str, type[Model]] = {}

	@classmethod
	def register(cls, key: str, model_cls: type[Model]):
		cls._registry[key] = model_cls

	@classmethod
	def create_model(
		cls,
		model_name: str = 'gemini-2.0-flash',
		temperature: float = 0.6,
		top_p: float = 0.6,
		top_k: int = 30,
		max_retries: int = 3,
		platform: str = 'openai',
		thinking_budget: int = 500,
		**kwargs,
	) -> Any:
		model_type = cls._get_type(model_name, platform)
		if model_type not in cls._registry:
			raise ValueError(f'No model registered under key: {model_type}')

		return cls._registry[model_type].create_model(
			model_name=model_name,
			temperature=temperature,
			top_p=top_p,
			top_k=top_k,
			max_retries=max_retries,
			thinking_budget=thinking_budget,
			**kwargs,
		)

	@staticmethod
	def _get_type(model_name: str, platform: str) -> str:
		name = model_name.lower()
		platform = platform.lower()

		if 'gpt' in name and platform == 'azure':
			return 'azure_gpt'
		elif 'gpt' in name and platform == 'openai':
			return 'openai_gpt'
		elif 'gemini' in name:
			return 'google_gemini'
		else:
			raise ValueError(
				f'Unknown model type for name: {model_name}, platform: {platform}'
			)


# ===== Register Models =====
ModelFactory.register('azure_gpt', AzureModel)
ModelFactory.register('openai_gpt', GptModel)
ModelFactory.register('google_gemini', GeminiModel)
