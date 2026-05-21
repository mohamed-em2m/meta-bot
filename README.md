# 🚀 Meta App Chatbot - Advanced WhatsApp AI Agent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)

An asynchronous, high-concurrency WhatsApp,Facebook,Instagram AI agent framework designed for production. Built with **Multi-LLM support (GPT-5, Gemini 2.5)**, **RAG (BigQuery)**, and **modular tool-agents**.

[**View Detailed Documentation 📖**](docs/index.md)

---

## ✨ Key Features

* **Advanced Reasoning**: Leverages cutting-edge models like `gpt-5-mini` and `gemini-2.5-flash`.
* **BigQuery RAG**: Real-time Retrieval-Augmented Generation for specialized domain knowledge.
* **Modular Architecture**: Features a clean router-based design for webhooks, messaging, and media.
* **Modular Tool System**: Easily extendable agents with custom tools using `@tool` decorators.
* **Fully Asynchronous**: Built with FastAPI and `httpx` for high-performance I/O.
* **Multi-Platform Support**: Unified message processing for both WhatsApp Cloud API and Facebook Page.
* **🔥 Dynaconf Powered**: Robust configuration management with `.toml` support and environment overrides.
* **🧪 Persistent Caching**: Efficient session and state management.

---

## 📁 Project Structure

```text
.
├── meta_app_chatbot/
│   ├── agent/                 # Core AI Logic (Main Agent & Tools)
│   ├── db/                    # Database & RAG Factory
│   │   ├── firestore/         # Firestore DB controllers
│   │   └── rag/               # BigQuery RAG implementations
│   ├── config/                # Centralized configuration (Settings & Schemas)
│   ├── routers/               # FastAPI Routers (Webhook, Messages, Media)
│   ├── prompts/               # Structured LLM instructions (.md templates)
│   ├── voice/                 # Audio processing and Voice-to-Text
│   └── main.py                # App entrypoint & Router registration
├── Dockerfile                 # Production-ready containerization
└── pyproject.toml             # Dependency management
```

---

## ⚙️ Getting Started

### 1. Installation

Requires [Python 3.12](https://www.python.org/downloads/) or higher.

```bash
# Clone the repository
git clone https://github.com/yourusername/meta-app-chatbot.git
cd meta-app-chatbot

# Set up virtual environment
python -m venv .venv
source .venv/bin/activate  # Or `.venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration

Professional configuration is managed via **Dynaconf**.

1. Navigate to `meta_app_chatbot/config/`.
2. Duplicate `settings.toml.example` and name it `settings.toml`.
3. Fill in your API keys and Meta App credentials:

```toml
# meta_app_chatbot/config/settings.toml

[default]
OPENAI_API_KEY = "sk-..."
GEMINI_API_KEY = "AIza..."
WHATSAPP_ACCESS_TOKEN = "EAA..."
```

> [!TIP]
> You can also use environment variables by prefixing them with `DYNACONF_` (e.g., `DYNACONF_OPENAI_API_KEY`).

---

## 🚀 Usage

### Running Locally

To start the FastAPI server:

```bash
python meta_app_chatbot/main.py
```

### 📡 API Endpoints

* `GET /webhook`: Meta Webhook verification.
* `POST /webhook`: Inbound message handler (WhatsApp/Facebook).
* `POST /store_messages`: Bulk store conversation history in Firestore.
* `POST /get_top_messages`: Retrieve recent conversation context.
* `GET /get_audio`: Retrieve temporary audio files.
* `GET /get_image`: Retrieve temporary image files.

---

## 🧠 Architecture Highlights

### Router-Based Design

The application is split into specialized routers for better maintainability:
* **Webhook Router**: Decouples platform-specific payload extraction from core agent logic.
* **Messages Router**: Handles all stateful persistence with Firestore.
* **Media Router**: Provides a secure way to serve temporary assets.

### Multi-Agent Reasoning

The system uses a primary agent that can delegate tasks to specialized sub-agents or use tools to interact with external services like Odoo, BigQuery, or the WhatsApp API itself.

### Optimized RAG

The RAG pipeline utilizes BigQuery for scalable document storage and vector-based retrieval, ensuring the AI agent always has access to the most recent and relevant data.

---

## 🐳 Deployment

The project is containerized for easy deployment to **Google Cloud Run**, **AWS Fargate**, or any standard Kubernetes cluster.

```bash
# Build the image
docker build -t meta-chatbot .

# Run the container
docker run -p 8080:8080 --env-file .env meta-chatbot
```

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git checkout origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.

---

<p align="center">Made with ❤️ for the Open Source Community</p>
