import re
import os
import uuid
import json
import base64
import hashlib
import inflect
import calendar
import tiktoken
import vertexai
import traceback
from datetime import datetime
import google.auth.transport.requests
from google.oauth2 import service_account
from fastapi.responses import JSONResponse

p = inflect.engine()


def get_access_token(SERVICE_ACCOUNT_FILE):
    """Fetches an OAuth2 access token from the service account credentials."""
    try:
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        auth_request = google.auth.transport.requests.Request()
        credentials.refresh(auth_request)
        return credentials.token
    except FileNotFoundError:
        print(f"ERROR: Service account key file not found at '{SERVICE_ACCOUNT_FILE}'.")
        print(
            "Please ensure the path is correct and the file exists, or set GOOGLE_APPLICATION_CREDENTIALS environment variable."
        )
        return None
    except Exception as e:
        print(f"ERROR: Failed to load credentials or get token: {e}")
        print(
            "Ensure your service account JSON file is valid and has permissions (e.g., 'Vertex AI User')."
        )
        return None


def days_in_current_month():
    today = datetime.today()
    return calendar.monthrange(today.year, today.month)[1]


def bytes_2base64(byts):
    return base64.b64encode(byts).decode("utf-8")


def base64_2bytes(base64_str: str):
    return base64.b64decode(base64_str.encode("utf-8"))


def check_city_tables(
    txt_index, logger, city_id, exists=True, method_name="delete", logging=True
):
    tables_names = txt_index.get_tables()
    txt_table_id = f"{city_id}_txt"
    img_table_id = f"{city_id}_image"

    if exists:
        condition_tables = (
            txt_table_id not in tables_names and img_table_id not in tables_names
        )
        message = "non-existent"
    else:
        condition_tables = txt_table_id in tables_names and img_table_id in tables_names
        message = "already existent"

    if condition_tables:
        cities = {t.replace("_txt", "").replace("_image", "") for t in tables_names}
        if logging:
            logger.info(f"{message} City: {city_id} Tables in the database!")
        response_content = {
            "message": f"Can't {method_name} {message} city. Cities: {list(cities)}"
        }
        return False, JSONResponse(content=response_content, status_code=404)

    return True, None


def generate_cache_key(key: str = "ai_response:", payload: dict = {}) -> str:
    query_string = json.dumps(payload, sort_keys=True)
    return key + hashlib.sha256(query_string.encode()).hexdigest()


def generate_cache_key_md5(key: str = "ai_response:", payload: dict = {}) -> str:
    query_string = json.dumps(payload, sort_keys=True)
    return key + hashlib.md5(query_string.encode()).hexdigest()


def create_img_template(imgs):
    image_list = []
    for index, img in enumerate(imgs):
        print(img.keys())
        content = img.get("content") or img.get("Content")
        ext = img.get("Ext") or img.get("ext")
        description = img.get("Description") or img.get("description")
        if index == 0:
            image_list += [
                {"type": "text", "text": f"This is the orignal image {description}"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/{ext};base64,{content}"},
                },
            ]
            image_list += [
                {
                    "type": "text",
                    "text": "This is are candidate images compare each one to the orignal image and decide if any of following images are same as the",
                }
            ]
            continue
        image_list += [
            {
                "type": "text",
                "text": f"This is candidate  image num {index} the place is {description}",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/{ext};base64,{content}"},
            },
        ]

    return ("user", image_list)


def set_env_variables(path):
    with open(f"{path}", "r", encoding="utf-8") as file:
        j = json.load(file)
        for var in j.keys():
            os.environ[var] = str(j.get(var))  # Convert to strin


import logging

logger = logging.getLogger("meta_app_chatbot")

def log_print(level, message="", exception=None, details=None):
    """Helper function for structured logging using standard logging module"""
    level_lower = str(level).lower()
    log_msg = message
    if details:
        log_msg += f" | Details: {details}"
    if exception:
        log_msg += f" | Exception: {exception}"
    
    if level_lower == "error":
        logger.error(log_msg, exc_info=exception)
    elif level_lower in ("warn", "warning"):
        logger.warning(log_msg)
    elif level_lower == "info":
        logger.info(log_msg)
    elif level_lower == "debug":
        logger.debug(log_msg)
    else:
        logger.info(f"[{level}] {log_msg}")


encoding = tiktoken.get_encoding("cl100k_base")


def get_token_length(x):
    return len(encoding.encode(x))


def setup_bq_creds(bq_cred_path: str):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = bq_cred_path


def generate_access_key() -> str:
    return uuid.uuid4().hex  # 32-character lowercase hex string


def markdown_to_facebook_format(text: str) -> str:
    # Convert code blocks (```code```)
    text = re.sub(r"```([\s\S]+?)```", r"```\n\1\n```", text)

    # Convert inline code (`code`)
    text = re.sub(r"`([^`\n]+?)`", r"`\1`", text)

    # Convert bold (**bold**)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)

    # Convert italic (*italic*) – avoid bold conflicts
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"_\1_", text)

    # Convert strikethrough (~~text~~)
    text = re.sub(r"~~(.+?)~~", r"~\1~", text)

    return text


def setup_image_api():
    vertexai.init(
        project=os.environ["PROJECT_ID"], api_key=os.environ["Gemini_API_KEY"]
    )


def create_messages_to_ai_format(messages: list, remove_role: str = ""):
    """
    Convert a list of messages into the format expected by the AI model.
    Each message should be a dictionary with 'role' and 'content' keys.
    """
    formatted_messages = []
    last_role = None
    composed_messages = ""
    for index, message in enumerate(messages):
        role = message.get("role", "user")
        if role == remove_role:
            continue
        time = message.get("time")
        content = message.get("text", "") or message.get("content", "")
        composed_messages += "\n" + content
        if last_role != role:
            formatted_messages.append(
                {
                    "role": role,
                    "content": f"this is message num {index} and happend at {time}"
                    + composed_messages,
                }
            )
            last_role = role
            composed_messages = ""
    if composed_messages != "":
        formatted_messages.append(
            {
                "role": role,
                "content": f"this is message num {index} and happend at {time}"
                + composed_messages,
            }
        )

    return formatted_messages


def number_to_ordinal_word(n):
    return p.ordinal(p.number_to_words(n))


def create_messages_to_ai_format_v2(
    messages: list, remove_role: str = "", return_last_user=False
):
    """
    Convert a list of messages into the format expected by the AI model.
    Each message should be a dictionary with 'role' and 'content' keys.
    """
    formatted_messages = []
    first_role = messages[0]["role"]
    last_time = messages[0]["time"]
    last_role = first_role
    composed_messages = ""
    index = 1
    for message in messages:
        role = message.get("role", "user")
        if role == remove_role:
            continue

        time = message.get("time")
        content = message.get("text", "") or message.get("content", "")

        if last_role != role:
            formatted_messages.append(
                {
                    "role": last_role,
                    "content": f"{number_to_ordinal_word(index)} message , happend at {last_time}\ncontent: "
                    + composed_messages,
                }
            )
            last_role = role
            composed_messages = ""
            index += 1
        last_time = time
        composed_messages = composed_messages + content + " "

    if composed_messages != "":
        formatted_messages.append(
            {
                "role": last_role,
                "content": f"this is Last message , happend at {last_time}\ncontent: "
                + composed_messages,
            }
        )
    if last_role == "user" and return_last_user:
        return formatted_messages, composed_messages
    return formatted_messages


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
