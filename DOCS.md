# 📖 Detailed Documentation

This document provides a deep dive into the architecture, configuration, and extensibility of the Meta App Chatbot framework.

---

## 🛠️ Configuration Reference

The project uses [Dynaconf](https://www.dynaconf.com/) for configuration. All settings are centrally managed in `meta_app_chatbot/config/settings.toml`.

### LLM Settings
| Key | Description |
| :--- | :--- |
| `OPENAI_API_KEY` | Your OpenAI secret key. |
| `GEMINI_API_KEY` | Google AI Studio (Gemini) API key. |
| `main_agent_model` | Primary model for complex reasoning (e.g., `gpt-4o`, `gemini-1.5-pro`). |
| `tool_agent_model` | Faster model used for tool selection and simple tasks. |
| `PLATFORM` | Directs the model factory to use a specific provider by default (`openai` or `gemini`). |

### Meta / WhatsApp Credentials
| Key | Description |
| :--- | :--- |
| `WHATSAPP_ACCESS_TOKEN` | Temporary or Perpetual System User token from Meta Developer Portal. |
| `WHATSAPP_PHONE_NUMBER_ID` | The unique ID of your WhatsApp Business number. |
| `VERIFY_TOKEN` | A custom string you define to verify your webhook with Meta. |
| `firebase_path` | Path to your Firebase service account JSON key. |

### RAG & Database
| Key | Description |
| :--- | :--- |
| `PROJECT_ID` | Your Google Cloud Project ID. |
| `RAG_DB` | BigQuery dataset name containing your vectorized info. |
| `RAG_TABLE` | BigQuery table name for RAG lookups. |
| `DEFUALT_USER_DB_NAME` | The main Firestore collection for storing user messages. |

---

## 🧠 Agentic Architecture

The framework follows a **Modular Agent** pattern.

### 1. Main Agent (`agent/main_agent.py`)
The orchestrator. It receives a message, analyzes the intent, and decides whether to:
- Respond directly using the system prompt.
- Call a specialized **Tool** (e.g., Odoo search).
- Delegate to a **Sub-Agent**.

### 2. Tools & Utilities
Tools are standard Python functions decorated with `@tool` (or handled via LangChain-style interfaces). 
- **WhatsApp Tool**: Handles the formatting and sending of outbound messages.
- **Odoo Tool**: Performs real-time inventory or CRM lookups.

### 3. Prompt Management
All system instructions are stored in the `/prompts` directory as Markdown files. This allows for:
- Version-controlled prompts.
- Easy experimentation without touching Python code.
- Dynamic prompt injection based on conversation state.

---

## 📚 Database Strategy

### Firestore (Conversation State)
The system uses Firestore to maintain conversation history across turns. 
- **Persistence**: Messages are stored in a nested structure: `conversations/{phone_number}/messages/{message_id}`.
- **Context Window**: When a new message arrives, the `Messages Router` retrieves the last `N` messages to build the message history for the LLM.

### BigQuery (RAG)
Used for deep domain knowledge (e.g., real estate listings, technical documentation).
- The `BigQueryRAG` class performs similarity searches on your indexed data.
- The results are injected into the agent's context as "Knowledge Base" facts.

---

## 🚀 Adding New Capabilities

### How to add a new Tool
1. Create a new function in `meta_app_chatbot/agent/tools/`.
2. Ensure it handles its own error states and returns a string or dictionary.
3. Register the tool in `main_agent.py` or the appropriate sub-agent's tool list.

### How to update a Prompt
1. Find the relevant `.md` file in `meta_app_chatbot/prompts/`.
2. Modify the instructions and save.
3. The next agent invocation will automatically load the updated template.

---

## 📬 Webhook Flow

1. **Inbound**: Meta sends a POST request to `/webhook`.
2. **Extraction**: `routers/webhook.py` parses the platform-specific JSON (WhatsApp vs FB).
3. **Async Processing**: A background task is spawned to avoid Meta's 3-second timeout.
4. **Agent Logic**: The agent processes the message, performs tool calls, and generates a response.
5. **Outbound**: The `send_whatsapp_message` tool sends the reply via the Cloud API.

---

## 🐳 Deployment Checklist

- [ ] Firebase Service Account Key added to `meta_app_chatbot/config/`.
- [ ] GCP Credentials configured for BigQuery access.
- [ ] `settings.toml` filled with production API keys.
- [ ] Port 8080 exposed in your cloud provider.
- [ ] WhatsApp Webhook configured in the Meta Dashboard with the correct `VERIFY_TOKEN`.
