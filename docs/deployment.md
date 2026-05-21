# 🚀 Deployment & Setup

This guide will help you deploy the Meta App Chatbot to a production environment, specifically focusing on Google Cloud Run.

---

## 🏗️ Prerequisites

1. **Meta Developer Account**: Create an app and set up the WhatsApp product.
2. **Google Cloud Project**: Enabled with BigQuery and Firestore.
3. **Docker**: Installed locally for building the image.

---

## 🛠️ Local Development

```bash
# 1. Clone and Install
git clone https://github.com/your-repo/meta-app-chatbot.git
cd meta-app-chatbot
pip install -r requirements.txt

# 2. Configure
cp meta_app_chatbot/config/settings.toml.example meta_app_chatbot/config/settings.toml
# Edit settings.toml with your keys

# 3. Run
python meta_app_chatbot/main.py
```

---

## 🐳 Docker Deployment

The provided `Dockerfile` uses a multi-stage build to ensure a slim runtime image.

```bash
# Build the image
docker build -t meta-chatbot .

# Run the container locally to test
docker run -p 8080:8080 --env-file .env meta-chatbot
```

---

## ☁️ Google Cloud Run (Recommended)

1. **Push to Artifact Registry**:

   ```bash
   docker tag meta-chatbot gcr.io/[PROJECT_ID]/meta-chatbot
   docker push gcr.io/[PROJECT_ID]/meta-chatbot
   ```

2. **Deploy**:
   Deploy the image via the Google Cloud Console or CLI. Ensure you set the `PORT` to `8080`.

3. **Webhook Configuration**:
   After deployment, Meta will provide a service URL. Add `/webhook` to this URL and use it in your Meta Dashboard.

---

## 📬 Webhook Troubleshooting

* **Verification Failed**: Ensure your `VERIFY_TOKEN` in Meta matches exactly with the one in `settings.toml`.
* **Timeout (500 Error)**: Meta requires a response within 3 seconds. The project handles this by using `asyncio.create_task` to process the message in the background while immediately returning a `200 OK`.
* **Permissions**: Ensure your Meta App has the `messages` and `messaging_postbacks` subscriptions enabled.
