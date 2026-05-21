# ⚙️ Configuration Guide

The project uses [Dynaconf](https://www.dynaconf.com/) to manage hierarchical settings.

!!! danger "Security Reminder"
    Never commit your `settings.toml` with real secrets to public repositories. Use environment variables or secret managers in production.

---

## 📄 settings.toml Reference

All settings are located in `meta_app_chatbot/config/settings.toml`.

### 🤖 LLM Strategy

| Key | Default | Description |
| :--- | :--- | :--- |
| `main_agent_model` | `gpt-4o-mini` | The workhorse model for complex reasoning. |
| `tool_agent_model` | `gemini-2.0-flash` | The faster model used for tool identification. |
| `PLATFORM` | `openai` | Default provider (`openai`, `gemini`, `vertex`). |

### 📱 Meta API

| Key | Description |
| :--- | :--- |
| `WHATSAPP_ACCESS_TOKEN` | Your Meta System User Access Token. |
| `WHATSAPP_PHONE_NUMBER_ID` | The ID of your WhatsApp phone number. |
| `VERIFY_TOKEN` | Custom string used to verify your webhook. |

---

## 🌍 Environment Variables

Override any `.toml` setting by prefixing with `DYNACONF_`.

```bash title="Example: Override API Key"
export DYNACONF_OPENAI_API_KEY="sk-..."
```

---

## 🔒 Security Best Practices

1. **Template First**: Use `settings.toml.example` as a template for team members.
2. **Secret Manager**: Use **Google Secret Manager** for production keys.
3. **Volume Mounts**: In Docker, mount service account keys instead of baking them into the image.
