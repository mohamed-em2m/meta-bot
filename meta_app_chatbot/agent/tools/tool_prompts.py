import pathlib
from langchain_core.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    ChatPromptTemplate,
)
from dynaprompt import DynaPrompt

# Path to the prompts directory
PROMPTS_DIR = pathlib.Path(__file__).parent.parent.parent / "prompts"
prompts = DynaPrompt(settings_files=[str(PROMPTS_DIR)])

# Define templates using DynaPrompt
system_prompt_dynamic = prompts.system_prompt_dynamic.template
user_prompt_dynamic = prompts.user_prompt_dynamic.template

system_template_summarize = ChatPromptTemplate.from_messages(
    [
        SystemMessagePromptTemplate.from_template(system_prompt_dynamic, template_format="jinja2"),
        HumanMessagePromptTemplate.from_template(user_prompt_dynamic, template_format="jinja2"),
    ]
)
