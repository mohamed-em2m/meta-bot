# 🏗️ Architecture & Core Logic

The Meta App Chatbot is designed as a **Modular Agent Framework**. Unlike simple request-response bots, it uses a reasoning loop to decide how to handle each message.

---

## 🧩 Core Components

### 1. The Main Agent Orchestrator

The `Main Agent` is the brain of the system. Its primary responsibilities include:

* **Intent Extraction**: Understanding what the user wants.
* **Context Management**: Retrieving historical messages from Firestore to maintain conversation flow.
* **Tool Dispatching**: Selecting the right tool for the job.

### 2. Multi-LLM Model Factory

The system is model-agnostic. Via the `Model Factory`, you can swap between:

* **OpenAI**: GPT-4o, GPT-5 (future-ready).
* **Google Gemini**: Gemini 1.5 Pro, 2.5 Flash.
* **Vertex AI**: Enterprise-grade Google Cloud LLMs.

### 3. BigQuery RAG Pipeline

Retrieval-Augmented Generation (RAG) empowers the agent with domain-specific knowledge without fine-tuning.

* **Indexing**: Data is stored in BigQuery tables.
* **Retrieval**: When a query arrives, the `BigQueryRAG` class fetches relevant context based on vector similarity.
* **Injection**: This context is added to the system prompt as "Ground Truth Facts."

---

## 🛠️ Extending Tools

Adding a new tool is straightforward. A tool is a Python function that the agent can "call."

### Example Tool Template

```python
@tool
def check_inventory(product_name: str) -> str:
    """Useful for checking if a product is in stock."""
    # Your logic here (e.g., API call to Odoo or Database)
    return f"We have 10 units of {product_name} in stock."
```

### Registration

Tools are registered within the agent's reasoning loop, allowing the LLM to understand when and how to use them based on the function's docstring.

---

## 🔄 The Reasoning Loop

1. **Payload Intake**: Webhook receives a message.
2. **State Retrieval**: Fetch last 10 messages from Firestore.
3. **Prompt Assembly**: Combine System Prompt + RAG Context + History + User Message.
4. **LLM Call**: Agent decides to use a Tool or respond.
5. **Execution**: Tool runs, results are fed back to LLM.
6. **Final Response**: Agent sends the formatted reply back via WhatsApp/Facebook.
