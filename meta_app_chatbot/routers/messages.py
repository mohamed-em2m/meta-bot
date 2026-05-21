import uuid

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from google.cloud import firestore

from meta_app_chatbot.agent.utils import log_print

from .schemas import GetTopMessagesRequest, StoreMessagesRequest

router = APIRouter()
db = firestore.Client()


@router.post('/store_messages')
async def store_message(payload: StoreMessagesRequest):
	success = []

	for message in payload.messages:
		try:
			wa_num = message.wa_num
			sender = message.sender
			text = message.text
			message_type = message.message_type
			message_id = message.message_id or str(uuid.uuid4())
			timestamp = message.time or firestore.SERVER_TIMESTAMP

			message_data = {
				'sender': sender,
				'text': text,
				'timestamp': timestamp,
				'message_type': message_type,
			}

			db.collection('conversations').document(wa_num).collection(
				'messages'
			).document(message_id).set(message_data)

			print(f'Message stored under conversation {wa_num} with ID {message_id}')
			success.append({'message_id': message_id, 'state': True})

		except Exception as e:
			log_print('Error', f'Error happened in store_message: {e}')
			success.append(
				{
					'message_id': getattr(message, 'message_id', 'unknown'),
					'state': False,
				}
			)

	return JSONResponse(status_code=200, content=success)


@router.post('/get_top_messages')
async def get_recent_messages(payload: GetTopMessagesRequest):
	wa_num = payload.wa_num
	top = payload.top

	try:
		messages_ref = (
			db.collection('conversations')
			.document(wa_num)
			.collection('messages')
			.order_by('timestamp', direction=firestore.Query.DESCENDING)
			.limit(top)
		)

		docs = messages_ref.stream()
		messages = [doc.to_dict() for doc in docs]

		# Return in chronological order (oldest to newest)
		return JSONResponse(status_code=200, content=list(reversed(messages)))

	except Exception as e:
		log_print('Error', f'Error fetching messages: {e}')
		return JSONResponse(status_code=500, content={'error': str(e)})
