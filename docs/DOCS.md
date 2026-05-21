# 📖 Complete Project Reference

This document serves as a comprehensive guide to the **Meta App Chatbot**. For specific sections, you can also refer to the individual guides in the `docs/` folder.

---

## 🗺️ Documentation Map

* [**🏗️ Architecture**](architecture.md): Deep dive into reasoning loops and tools.
* [**⚙️ Configuration**](configuration.md): Full settings reference.
* [**🚀 Deployment**](deployment.md): How to launch in production.

---

## 🌟 Project Vision

The goal of this project is to provide a production-ready, highly extensible AI Agent for Meta platforms (WhatsApp, Facebook). It is built to handle thousands of concurrent conversations while maintaining a "brain" that can access company data (RAG) and perform real-world tasks (Tools).

---

## 🛠️ Core Stack

* **Logic**: [FastAPI](https://fastapi.tiangolo.com/) (Async/High Performance)
* **Intelligence**: [Google Gemini](https://deepmind.google/technologies/gemini/) & [OpenAI GPT-4/5](https://openai.com/)
* **Knowledge Base**: [Google BigQuery](https://cloud.google.com/bigquery) (Vector RAG)
* **State Management**: [Google Firestore](https://cloud.google.com/firestore)
* **Configuration**: [Dynaconf](https://www.dynaconf.com/)

---

## 🧬 Data Flow Architecture

1. **Incoming**: Meta Webhook (WhatsApp/FB/IG Message)
2. **Dispatcher**: FastAPI Router extracts text/audio and sender info.
3. **State Manager**: Firestore retrieves the recent message history.
4. **Knowledge Retrieval**: BigQuery finds relevant facts based on user query.
5. **Reasoning**: LLM analyzes context and decides to:
   * Call a **Tool** (e.g., Odoo search, Shipping tracking).
   * Formulate a direct reply.
6. **Action**: Outbound message sent via Meta Cloud API.

---

## 🤝 Open Source & Contributing

We welcome contributions! Please see our [main README](../README.md#🤝-contributing) for guidelines on how to submit pull requests.

---

Made with ❤️ for the AI Community
