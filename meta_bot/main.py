import asyncio
import logging

from fastapi import FastAPI
from meta_app_chatbot.agent.utils import setup_image_api
from meta_app_chatbot.routers import media, messages, webhook
from meta_app_chatbot.utils.logger import setup_logging

# Setup logging and image API
setup_logging()
setup_image_api()

# Attempt to use uvloop for performance
try:
	import uvloop

	asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
	pass

app = FastAPI(title='Meta App Chatbot')

# Basic configuration
logging.basicConfig(level=logging.INFO)

# Include routers
app.include_router(webhook.router, tags=['Webhook'])
app.include_router(messages.router, tags=['Messages'])
app.include_router(media.router, tags=['Media'])


@app.get('/', tags=['General'])
async def root() -> dict[str, str]:
	return {'message': 'WhatsApp AI Agent is running.'}


if __name__ == '__main__':
	import uvicorn

	uvicorn.run(app, host='0.0.0.0', port=8000)
