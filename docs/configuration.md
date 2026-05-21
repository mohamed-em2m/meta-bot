# ⚙️ Configuration Guide

The project uses [Dynaconf](https://www.dynaconf.com/) to manage hierarchical settings. This allows you to easily switch between development and production environments.

---

## 📄 settings.toml Reference

All settings are located in `meta_app_chatbot/config/settings.toml`.

### 🤖 LLM Strategy

| Key | Default | Description |
| :--- | :--- | :--- |
| `main_agent_model` | `gpt-5-mini` | The workhorse model for complex reasoning. |
| `tool_agent_model` | `gemini-2.5-flash` | The faster model used for tool identification. |
| `PLATFORM` | `openai` | Default provider (`openai`, `gemini`, `vertex`). |

### 📱 Meta API (WhatsApp/Facebook)

| Key | Description |
| :--- | :--- |
| `WHATSAPP_ACCESS_TOKEN` | Your Meta System User Access Token. |
| `WHATSAPP_PHONE_NUMBER_ID` | The ID of your WhatsApp phone number. |
| `VERIFY_TOKEN` | The custom string used to verify your webhook in the Meta dashboard. |

### 🗄️ Database & Cloud

| Key | Description |
| :--- | :--- |
| `PROJECT_ID` | Your Google Cloud Project ID. |
| `firebase_path` | Absolute path to your Firebase service account JSON. |
| `RAG_DB` | BigQuery dataset for your knowledge base. |
| `RAG_TABLE` | BigQuery table for knowledge vector lookups. |

---

## 🌍 Environment Variables

You can override any `.toml` setting using environment variables. Prefix the variable name with `DYNACONF_`.

**Example:**

To override the OpenAI API Key in production:

```bash
export DYNACONF_OPENAI_API_KEY="sk-..."
```

---

## 🔒 Security Best Practices

1. **Never commit `settings.toml`** if it contains real secrets. Use `settings.toml.example` as a template.
2. Use **Google Secret Manager** or `.env` files for production keys.
3. Ensure your `FIREBASE_PATH` points to a secure location, ideally handled via a volumes mount in Docker.
