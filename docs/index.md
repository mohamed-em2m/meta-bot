# 📚 Meta App Chatbot Documentation

Welcome to the official documentation for the **Meta App Chatbot**. This guide provides everything you need to build, deploy, and extend your own high-concurrency WhatsApp AI agent.

!!! info "Agentic Framework"
    The **Meta App Chatbot** is not just a chatbot—it's an agentic framework. It combines advanced reasoning, persistent memory, and scalable knowledge.

## 🧭 Navigation

- [:material-family-tree: **Architecture & Core Logic**](architecture.md)
  - Learn about the Multi-Agent system, RAG implementation, and the reasoning loop.
- [:material-cog: **Configuration Guide**](configuration.md)
  - Detailed breakdown of LLM settings, Meta API credentials, and Database configurations.
- [:material-rocket-launch: **Deployment & Setup**](deployment.md)
  - Step-by-step guide on how to go from local development to production on Google Cloud Run.
- [:material-tools: **Tool Development**](architecture.md#extending-tools)
  - How to create custom tools to give your agent new superpowers.

---

## 🌟 Quick Overview

The framework is built on four core pillars:

1. **Reasoning**: Cutting-edge models like GPT-4o and Gemini 2.0.
2. **Memory**: Persistent conversation state in Firestore.
3. **Knowledge**: Scalable domain knowledge via BigQuery RAG.
4. **Action**: Real-world integration via modular tools (Odoo CRM, Meta Messaging).

---

## 📬 Getting Support

If you encounter issues or have questions:

1. Check the [Configuration Guide](configuration.md) for common setup errors.
2. Review the [Architecture](architecture.md) to understand state management.
3. [Open an issue on GitHub](https://github.com/mohamed-em2m/meta-bot/issues).
