# 🚀 Deployment & Setup

This guide will help you deploy the Meta App Chatbot to a production environment.

---

## 🏗️ Prerequisites

- **Meta Developer Account**: Create an app and set up the WhatsApp/Facebook products.
- **Google Cloud Project**: Enabled with BigQuery and Firestore.
- **Docker**: Installed locally for building the image.

---

## 🛠️ Local Development

=== "Step 1: Clone"

    ```bash
    git clone https://github.com/mohamed-em2m/meta-bot.git
    cd meta-bot
    ```

=== "Step 2: Environment"

    ```bash
    uv sync
    source .venv/bin/activate
    ```

=== "Step 3: Run"

    ```bash
    python meta_app_chatbot/main.py
    ```

---

## 🐳 Docker Deployment

The provided `Dockerfile` uses a multi-stage build to ensure a slim runtime image.

```bash title="Build and Run"
# Build the image
docker build -t meta-chatbot .

# Run the container locally
docker run -p 8080:8080 --env-file .env meta-chatbot
```

---

## ☁️ Google Cloud Run

!!! info "Recommended Pattern"
    We recommend using Google Cloud Run for its seamless integration with Firestore and BigQuery and its ability to scale to zero.

1. **Push to Artifact Registry**:

    ```bash
    docker tag meta-chatbot gcr.io/[PROJECT_ID]/meta-chatbot
    docker push gcr.io/[PROJECT_ID]/meta-chatbot
    ```

2. **Deploy Command**:

    ```bash
    gcloud run deploy meta-chatbot \
      --image gcr.io/[PROJECT_ID]/meta-chatbot \
      --platform managed \
      --port 8080
    ```

---

## 📬 Webhook Troubleshooting

??? bug "Common Issues"
    - **Verification Failed**: Ensure your `VERIFY_TOKEN` matches exactly.
    - **Timeout (500 Error)**: Meta requires a response within 3 seconds. The project handles this via background tasks.
    - **Permissions**: Ensure your Meta App has `messages` and `messaging_postbacks` enabled.
