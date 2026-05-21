import asyncio

import firebase_admin
from firebase_admin import credentials, firestore

from meta_app_chatbot.agent.utils import log_print
from meta_app_chatbot.config.settings import settings

# Use a service account.
cred = credentials.Certificate(settings.get('firebase_path'))

app = firebase_admin.initialize_app(cred)


class FirestoreChatService:
	def __init__(self, database=None):
		if database is None:
			database = settings.get('DEFUALT_USER_DB_NAME')
		self.db = firestore.Client(database=database)

	async def store(self, collection_id: str, document_id: str, payloads: list | dict):
		success = []
		loop = 0
		if isinstance(payloads, dict):
			payloads = [payloads]
			loop = ''
		for payload in payloads:
			try:
				if len(payloads) > 1:
					self.db.collection(collection_id).document(
						document_id + f'{loop}'
					).set(payload)
					success.append(
						{'message_id': document_id + f'{loop}', 'state': True}
					)
				else:
					self.db.collection(collection_id).document(document_id).set(payload)
					success.append({'message_id': document_id, 'state': True})
			except Exception as e:
				log_print(
					'Error', f'error happend while storing message {collection_id}: {e}'
				)

				success.append({'message_id': collection_id, 'state': False})
			log_print('info', 'Message stored in Firestore')
			if not isinstance(loop, str):
				loop += 1
		return success

	async def store_document(
		self, firestore_id: str, firstore_document_id: str, messages: list
	):
		success = []
		for message in messages:
			try:
				self.db.collection(firestore_id).document(firstore_document_id).set(
					message
				)

				success.append({'message_id': firstore_document_id, 'state': True})
			except Exception as e:
				log_print(
					'Error',
					f'error happend while storing message {message.get("message_id", "unknown")}: {e}',
				)

				success.append(
					{'message_id': message.get('message_id', 'unknown'), 'state': False}
				)
			log_print('info', 'Message stored in Firestore')
		return success

	async def get_recent_messages(self, firestore_id: str, top: int = 5):
		try:
			messages_ref = (
				self.db.collection(firestore_id)
				.order_by('time', direction=firestore.Query.DESCENDING)
				.limit(top)
			)

			docs = messages_ref.stream()
			log_print('info', 'Get Data from FireStore')

			return list(
				reversed(
					[doc.to_dict() if doc.to_dict() is not None else {} for doc in docs]
				)
			)
		except Exception as e:
			raise RuntimeError(f'Error fetching messages: {e}')

	async def read(self, collection: str, id: str = ''):
		try:
			messages_ref = self.db.collection(collection).document(id)
			doc = messages_ref.get()
			log_print('info', 'Get Data from FireStore')
			return doc.to_dict() or {}
		except Exception as e:
			raise RuntimeError(f'Error fetching messages: {e}')

	def get_length(self, collection):
		try:
			collection_ref = self.db.collection(collection)
			count_query = collection_ref.count()
			count_result = count_query.get()
			count = count_result[0][0].value  # returns an integer
			return count
		except Exception as e:
			print(f'Error getting collection length: {e}')
			return 0

	def document_exists(self, collection_id: str, document_id: str) -> bool:
		doc_ref = self.db.collection(collection_id).document(document_id)
		doc = doc_ref.get()
		return doc.exists

	async def delete_certain_document(self, collection_id, id_document):
		log_print('info', 'Start deleting document from collection')

		doc_ref = self.db.collection(collection_id).document(id_document)
		doc_snapshot = doc_ref.get()

		if doc_snapshot.exists:
			doc_ref.delete()
			return True
		else:
			return False

	async def delete_document(self, doc):
		doc.reference.delete()

	async def delete_collection(self, collection_id):
		log_print('info', 'start deleteing collectton')
		docs = self.db.collection(collection_id).stream()
		await asyncio.gather(*[self.delete_document(doc) for doc in docs])
		log_print('info', 'end deleteing collectton')
		return True


class FirestoreFactory:
	_registry: dict[str, FirestoreChatService] = {}

	@classmethod
	def register(cls, name: str, instance: FirestoreChatService) -> None:
		"""
		Register a FirestoreChatService under the given name.
		"""
		if name in cls._registry:
			raise KeyError(f"Firestore service '{name}' is already registered")
		cls._registry[name] = instance

	@classmethod
	def get(cls, name: str) -> FirestoreChatService:
		"""
		Retrieve a registered FirestoreChatService by name.
		Raises KeyError if not found.
		"""
		try:
			return cls._registry[name]
		except KeyError:
			raise KeyError(f"No Firestore service registered under '{name}'")


# instantiate your services
billing_pool = FirestoreChatService(settings.get('DEFAULT_BILLING_POOL_DB_NAME'))
user_messages = FirestoreChatService(
	settings.get('DEFUALT_USER_DB_NAME')
)  # maybe default name inside
message_pool = FirestoreChatService(settings.get('DEFUALT_MESSAGES_POOL_DB_NAME'))

# register them
FirestoreFactory.register(settings.get('DEFAULT_BILLING_POOL_DB_NAME'), billing_pool)
FirestoreFactory.register(settings.get('DEFUALT_MESSAGES_POOL_DB_NAME'), message_pool)
FirestoreFactory.register(settings.get('DEFUALT_USER_DB_NAME'), user_messages)
