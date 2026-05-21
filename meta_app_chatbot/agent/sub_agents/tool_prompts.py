import pathlib
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from dynaprompt import DynaPrompt

# Path to the prompts directory
PROMPTS_DIR = pathlib.Path(__file__).parent.parent.parent / "prompts"
prompts = DynaPrompt(settings_files=[str(PROMPTS_DIR)])

# Define templates using DynaPrompt
system_prompt_odoo = prompts.system_prompt_odoo.template
user_prompt_odoo = prompts.user_prompt_odoo.template

odoo_query_templete = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt_odoo),
        MessagesPlaceholder("agent_scratchpad"),
        ("user", user_prompt_odoo),
    ]
)
