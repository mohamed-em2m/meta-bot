import traceback

from langchain.tools import tool

from meta_app_chatbot.agent.utils import log_print

from .whatsapp_send_messages import whatsapp


@tool
async def send_whatsapp_message(
	body: str, preview_url: bool = False, additions: dict = {}
) -> dict:
	"""
	Send a WhatsApp message to a user using the WhatsApp Cloud API.
	Args:
	    to (str): The recipient's WhatsApp number in international format (e.g., "1234567890").
	    body (str): The message text to send.
	    preview_url (bool, optional): Whether to show a URL preview in the message. Defaults to False.
	Returns:
	    dict:
	        success (bool): True if sent successfully
	        status (str): "sent" | "error",   # Textual status
	        message_id (str,optional) :ID of sent message, if successful
	        error (str,optional) : Error message, if failed

	Example:
	    send_whatsapp_message(to="1234567890", body="Hello!", preview_url=True)
	"""
	try:
		to = additions.get('wa_id')
		result = await whatsapp.send_text_message(
			to=to, body=body, preview_url=preview_url
		)

		return {
			'success': True,
			'status': 'sent',
			'message_id': result.get('messages', [{}])[0].get('id', None),
			'error': None,
		}
	except Exception as e:
		log_print(
			'ERROR',
			f'[WhatsAppTool] Failed to send message to {to}: {e},\nTraceback: {traceback.format_exc()}',
		)
		return {
			'success': False,
			'status': 'error',
			'message_id': None,
			'error': str(e),
		}
