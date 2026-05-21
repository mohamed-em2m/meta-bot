import pathlib

from dynaprompt import DynaPrompt
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    MessagesPlaceholder,
    SystemMessagePromptTemplate,
)
from pydantic import BaseModel

# Path to the prompts directory
PROMPTS_DIR = pathlib.Path(__file__).parent.parent / "prompts"
prompts = DynaPrompt(settings_files=[str(PROMPTS_DIR)])


class Summarize(BaseModel):
    thoughts: str | None = ""
    is_trivia_question: bool = False
    trivia_answer: str | None = "هاي"
    lang: str | None = ""
    voice_lang: str | None = "arabic"
    rag_query: str | None = "Merasi"


class divideClass(BaseModel):
    messages: list[str]


summarize_parser = PydanticOutputParser(pydantic_object=Summarize)
divied_text_parser = PydanticOutputParser(pydantic_object=divideClass)

# Load prompts dynamically from DynaPrompt

system_message = SystemMessagePromptTemplate.from_template(
    prompts.system_message.template, template_format="jinja2"
)

human_message = HumanMessagePromptTemplate.from_template(
    prompts.human_message.template, template_format="jinja2"
)

main_prompt = ChatPromptTemplate.from_messages(
    [
        system_message,
        MessagesPlaceholder(variable_name="conversation_history"),
        HumanMessagePromptTemplate.from_template(
            "{{ query }}", template_format="jinja2"
        ),
        human_message,
    ]
)

history_system_message = SystemMessagePromptTemplate.from_template(
    prompts.history_system_message.template, template_format="jinja2"
)

history_human_message = HumanMessagePromptTemplate.from_template(
    prompts.history_human_message.template, template_format="jinja2"
)

history_prompt = ChatPromptTemplate.from_messages(
    [history_system_message, history_human_message]
).partial(format_instructions=summarize_parser.get_format_instructions())

system_message_facts = SystemMessagePromptTemplate.from_template(
    prompts.system_message_facts.template, template_format="jinja2"
)

human_message_facts = HumanMessagePromptTemplate.from_template(
    prompts.human_message_facts.template, template_format="jinja2"
)

facts_extractor_prompt = ChatPromptTemplate.from_messages(
    [system_message_facts, human_message_facts]
)

system_divide_message = SystemMessagePromptTemplate.from_template(
    prompts.system_divide_message.template, template_format="jinja2"
)

human_divide_message = HumanMessagePromptTemplate.from_template(
    prompts.human_divide_message.template, template_format="jinja2"
)

divide_agent_prompt = ChatPromptTemplate.from_messages(
    [system_divide_message, human_divide_message]
).partial(format_instructions=divied_text_parser.get_format_instructions())

response_summarize_system = SystemMessagePromptTemplate.from_template(
    prompts.response_summarize_system.template, template_format="jinja2"
)

response_summarize_human = HumanMessagePromptTemplate.from_template(
    prompts.response_summarize_human.template, template_format="jinja2"
)

summarize_response_prompt = ChatPromptTemplate.from_messages(
    [response_summarize_system, response_summarize_human]
)

system_divide_audio = SystemMessagePromptTemplate.from_template(
    prompts.system_divide_audio.template, template_format="jinja2"
)

human_divide_audio = HumanMessagePromptTemplate.from_template(
    prompts.human_divide_audio.template, template_format="jinja2"
)

divide_audio_prompt = ChatPromptTemplate.from_messages(
    [system_divide_audio, human_divide_audio]
).partial(format_instructions=divied_text_parser.get_format_instructions())
