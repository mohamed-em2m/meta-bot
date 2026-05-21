import asyncio
import base64
import mimetypes
import os
from typing import Any

import aiofiles
import anyio
import httpx

from meta_app_chatbot.config.settings import settings


class MessengerClient:
	"""
	An enhanced async Python client for sending messages via the Facebook Messenger Send API.

	Features:
	- Send text messages
	- Send images with optional text
	- Send attachments (images, videos, audio, files)
	- Send quick replies
	- Send generic templates
	- Upload and reuse attachments
	- Robust error handling with retries
	- Each method uses its own httpx client context manager

	Usage:
	    client = MessengerClient(page_access_token="YOUR_PAGE_ACCESS_TOKEN")
	    await client.send_text_message(fb_sender_id="USER_PSID", text="Hello!")
	    await client.send_image_with_text(fb_sender_id="USER_PSID",
	                                    image_url="https://example.com/image.jpg",
	                                    text="Check this out!")
	"""

	GRAPH_API_URL = 'https://graph.facebook.com'
	MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB limit for attachments

	def __init__(self, page_access_token: str, version: str = 'v23.0'):
		self.page_access_token = page_access_token
		self.version = version
		self.base_url = f'{self.GRAPH_API_URL}/{self.version}/me/messages'
		self.upload_url = f'{self.GRAPH_API_URL}/{self.version}/me/message_attachments'
		self.timeout = httpx.Timeout(connect=30.0, read=60.0, write=60.0, pool=30.0)

	async def _post(
		self, payload: dict[str, Any], retries: int = 3, backoff_factor: float = 2
	) -> dict[str, Any]:
		"""Enhanced POST method with better error handling and logging."""
		params = {'access_token': self.page_access_token}

		for attempt in range(1, retries + 1):
			try:
				async with httpx.AsyncClient(timeout=self.timeout) as client:
					response = await client.post(
						self.base_url, params=params, json=payload
					)
					response.raise_for_status()
					return response.json()

			except httpx.HTTPStatusError as exc:
				error_data = exc.response.json() if exc.response.content else {}
				print(
					f'[Attempt {attempt}] HTTP {exc.response.status_code}: {error_data}'
				)

				# Don't retry on client errors (4xx)
				if 400 <= exc.response.status_code < 500:
					return {'error': error_data}

				if attempt == retries:
					return {'error': f'HTTP {exc.response.status_code}: {error_data}'}

				await asyncio.sleep(backoff_factor ** (attempt - 1))

			except (httpx.RequestError, httpx.TimeoutException) as exc:
				print(f'[Attempt {attempt}] Request failed: {exc}')
				if attempt == retries:
					return {'error': str(exc)}
				await asyncio.sleep(backoff_factor ** (attempt - 1))

	async def _upload_attachment(
		self, file_path: str, attachment_type: str, retries: int = 3
	) -> str | None:
		"""Upload an attachment and return its attachment_id for reuse."""
		try:
			# Validate file
			path = anyio.Path(file_path)
			if not await path.exists():
				raise FileNotFoundError(f'File not found: {file_path}')

			file_size = (await path.stat()).st_size
			if file_size > self.MAX_FILE_SIZE:
				raise ValueError(
					f'File too large: {file_size} bytes (max: {self.MAX_FILE_SIZE})'
				)

			# Determine MIME type
			mime_type, _ = mimetypes.guess_type(file_path)
			if not mime_type:
				mime_type = 'application/octet-stream'

			# Prepare upload data
			params = {'access_token': self.page_access_token}

			async with aiofiles.open(file_path, 'rb') as f:
				file_content = await f.read()

			{
				'message': (
					None,
					'{"attachment":{"type":"'
					+ attachment_type
					+ '","payload":{"is_reusable":true}}}',
					'application/json',
				),
				'filedata': (os.path.basename(file_path), file_content, mime_type),
			}

			# Upload with retry logic
			for attempt in range(1, retries + 1):
				try:
					async with httpx.AsyncClient(timeout=self.timeout) as client:
						# Convert to httpx-compatible format
						files_httpx = {
							'message': (
								'message',
								'{"attachment":{"type":"'
								+ attachment_type
								+ '","payload":{"is_reusable":true}}}',
								'application/json',
							),
							'filedata': (
								os.path.basename(file_path),
								file_content,
								mime_type,
							),
						}

						response = await client.post(
							self.upload_url, params=params, files=files_httpx
						)
						response.raise_for_status()

						result = response.json()
						return result.get('attachment_id')

				except (
					httpx.RequestError,
					httpx.HTTPStatusError,
					httpx.TimeoutException,
				) as e:
					print(f'[Upload Attempt {attempt}] Failed: {e}')
					if attempt == retries:
						print(f'Failed to upload attachment after {retries} attempts')
						return None
					await asyncio.sleep(2 ** (attempt - 1))

		except Exception as e:
			print(f'Failed to upload attachment: {e}')
			return None

	async def send_text_message(
		self, fb_sender_id: str, text: str, retries: int = 3
	) -> dict[str, Any]:
		"""Send a text message."""
		payload = {'recipient': {'id': fb_sender_id}, 'message': {'text': text}}

		params = {'access_token': self.page_access_token}

		for attempt in range(1, retries + 1):
			try:
				async with httpx.AsyncClient(timeout=self.timeout) as client:
					response = await client.post(
						self.base_url, params=params, json=payload
					)
					response.raise_for_status()
					return response.json()

			except httpx.HTTPStatusError as exc:
				error_data = exc.response.json() if exc.response.content else {}
				print(
					f'[Text Message Attempt {attempt}] HTTP {exc.response.status_code}: {error_data}'
				)

				if 400 <= exc.response.status_code < 500:
					return {'error': error_data}

				if attempt == retries:
					return {'error': f'HTTP {exc.response.status_code}: {error_data}'}

				await asyncio.sleep(2 ** (attempt - 1))

			except (httpx.RequestError, httpx.TimeoutException) as exc:
				print(f'[Text Message Attempt {attempt}] Request failed: {exc}')
				if attempt == retries:
					return {'error': str(exc)}
				await asyncio.sleep(2 ** (attempt - 1))

	async def send_image_with_text(
		self,
		fb_sender_id: str,
		image_url: str | None = None,
		image_path: str | None = None,
		text: str | None = None,
		reuse_attachment: bool = True,
	) -> dict[str, Any]:
		"""
		Send an image with optional accompanying text.

		Args:
		    fb_sender_id: Recipient's Facebook ID
		    image_url: URL of the image (either this or image_path required)
		    image_path: Local path to image file (either this or image_url required)
		    text: Optional text to send with the image
		    reuse_attachment: Whether to upload and reuse the attachment (only for local files)
		"""
		try:
			# Send image
			if image_path and reuse_attachment:
				# Upload and reuse attachment
				attachment_id = await self._upload_attachment(image_path, 'image')
				if attachment_id:
					image_response = await self.send_attachment(
						fb_sender_id=fb_sender_id,
						attachment_type='image',
						attachment_id=attachment_id,
					)
				else:
					# Fallback to URL method if upload fails
					if not image_url:
						return {'error': 'Failed to upload image and no URL provided'}
					image_response = await self.send_attachment(
						fb_sender_id=fb_sender_id,
						attachment_type='image',
						url=image_url,
					)
			elif image_url:
				# Send via URL
				image_response = await self.send_attachment(
					fb_sender_id=fb_sender_id, attachment_type='image', url=image_url
				)
			elif image_path:
				# Convert local file to data URL (less efficient but works)
				async with aiofiles.open(image_path, 'rb') as f:
					image_data = base64.b64encode(await f.read()).decode()
				mime_type, _ = mimetypes.guess_type(image_path)
				data_url = f'data:{mime_type};base64,{image_data}'

				image_response = await self.send_attachment(
					fb_sender_id=fb_sender_id, attachment_type='image', url=data_url
				)
			else:
				return {'error': 'Either image_url or image_path must be provided'}

			# Send text if provided
			if text and not image_response.get('error'):
				await asyncio.sleep(0.5)  # Small delay to ensure proper order
				text_response = await self.send_text_message(fb_sender_id, text)
				return {
					'image_response': image_response,
					'text_response': text_response,
					'success': not (
						image_response.get('error') or text_response.get('error')
					),
				}

			return image_response

		except Exception as e:
			return {'error': str(e)}

	async def send_attachment(
		self,
		fb_sender_id: str,
		attachment_type: str,
		url: str | None = None,
		attachment_id: str | None = None,
		file_path: str | None = None,
		retries: int = 3,
	) -> dict[str, Any]:
		"""
		Send an attachment (image, video, audio, or file).

		Args:
		    attachment_type: "image", "video", "audio", or "file"
		    url: URL of the attachment
		    attachment_id: Previously uploaded attachment ID
		    file_path: Local file path (will be uploaded)
		"""
		try:
			if file_path:
				# Upload file first
				attachment_id = await self._upload_attachment(
					file_path, attachment_type
				)
				if not attachment_id:
					return {'error': 'Failed to upload file'}

			if attachment_id:
				attachment_payload = {
					'type': attachment_type,
					'payload': {'attachment_id': attachment_id},
				}
			elif url:
				attachment_payload = {
					'type': attachment_type,
					'payload': {'url': url, 'is_reusable': True},
				}
			else:
				return {'error': 'Must provide url, attachment_id, or file_path'}

			payload = {
				'recipient': {'id': fb_sender_id},
				'message': {'attachment': attachment_payload},
			}

			params = {'access_token': self.page_access_token}

			for attempt in range(1, retries + 1):
				try:
					async with httpx.AsyncClient(timeout=self.timeout) as client:
						response = await client.post(
							self.base_url, params=params, json=payload
						)
						response.raise_for_status()
						return response.json()

				except httpx.HTTPStatusError as exc:
					error_data = exc.response.json() if exc.response.content else {}
					print(
						f'[Attachment Attempt {attempt}] HTTP {exc.response.status_code}: {error_data}'
					)

					if 400 <= exc.response.status_code < 500:
						return {'error': error_data}

					if attempt == retries:
						return {
							'error': f'HTTP {exc.response.status_code}: {error_data}'
						}

					await asyncio.sleep(2 ** (attempt - 1))

				except (httpx.RequestError, httpx.TimeoutException) as exc:
					print(f'[Attachment Attempt {attempt}] Request failed: {exc}')
					if attempt == retries:
						return {'error': str(exc)}
					await asyncio.sleep(2 ** (attempt - 1))

		except Exception as e:
			return {'error': str(e)}

	async def send_quick_replies(
		self,
		fb_sender_id: str,
		text: str,
		quick_replies: list[dict[str, Any]],
		retries: int = 3,
	) -> dict[str, Any]:
		"""Send a message with quick reply buttons."""
		payload = {
			'recipient': {'id': fb_sender_id},
			'message': {'text': text, 'quick_replies': quick_replies},
		}

		params = {'access_token': self.page_access_token}

		for attempt in range(1, retries + 1):
			try:
				async with httpx.AsyncClient(timeout=self.timeout) as client:
					response = await client.post(
						self.base_url, params=params, json=payload
					)
					response.raise_for_status()
					return response.json()

			except httpx.HTTPStatusError as exc:
				error_data = exc.response.json() if exc.response.content else {}
				print(
					f'[Quick Replies Attempt {attempt}] HTTP {exc.response.status_code}: {error_data}'
				)

				if 400 <= exc.response.status_code < 500:
					return {'error': error_data}

				if attempt == retries:
					return {'error': f'HTTP {exc.response.status_code}: {error_data}'}

				await asyncio.sleep(2 ** (attempt - 1))

			except (httpx.RequestError, httpx.TimeoutException) as exc:
				print(f'[Quick Replies Attempt {attempt}] Request failed: {exc}')
				if attempt == retries:
					return {'error': str(exc)}
				await asyncio.sleep(2 ** (attempt - 1))

	async def send_generic_template(
		self, fb_sender_id: str, elements: list[dict[str, Any]], retries: int = 3
	) -> dict[str, Any]:
		"""Send a generic template with cards."""
		payload = {
			'recipient': {'id': fb_sender_id},
			'message': {
				'attachment': {
					'type': 'template',
					'payload': {'template_type': 'generic', 'elements': elements},
				}
			},
		}

		params = {'access_token': self.page_access_token}

		for attempt in range(1, retries + 1):
			try:
				async with httpx.AsyncClient(timeout=self.timeout) as client:
					response = await client.post(
						self.base_url, params=params, json=payload
					)
					response.raise_for_status()
					return response.json()

			except httpx.HTTPStatusError as exc:
				error_data = exc.response.json() if exc.response.content else {}
				print(
					f'[Generic Template Attempt {attempt}] HTTP {exc.response.status_code}: {error_data}'
				)

				if 400 <= exc.response.status_code < 500:
					return {'error': error_data}

				if attempt == retries:
					return {'error': f'HTTP {exc.response.status_code}: {error_data}'}

				await asyncio.sleep(2 ** (attempt - 1))

			except (httpx.RequestError, httpx.TimeoutException) as exc:
				print(f'[Generic Template Attempt {attempt}] Request failed: {exc}')
				if attempt == retries:
					return {'error': str(exc)}
				await asyncio.sleep(2 ** (attempt - 1))

	async def send_button_template(
		self,
		fb_sender_id: str,
		text: str,
		buttons: list[dict[str, Any]],
		retries: int = 3,
	) -> dict[str, Any]:
		"""Send a button template."""
		payload = {
			'recipient': {'id': fb_sender_id},
			'message': {
				'attachment': {
					'type': 'template',
					'payload': {
						'template_type': 'button',
						'text': text,
						'buttons': buttons,
					},
				}
			},
		}

		params = {'access_token': self.page_access_token}

		for attempt in range(1, retries + 1):
			try:
				async with httpx.AsyncClient(timeout=self.timeout) as client:
					response = await client.post(
						self.base_url, params=params, json=payload
					)
					response.raise_for_status()
					return response.json()

			except httpx.HTTPStatusError as exc:
				error_data = exc.response.json() if exc.response.content else {}
				print(
					f'[Button Template Attempt {attempt}] HTTP {exc.response.status_code}: {error_data}'
				)

				if 400 <= exc.response.status_code < 500:
					return {'error': error_data}

				if attempt == retries:
					return {'error': f'HTTP {exc.response.status_code}: {error_data}'}

				await asyncio.sleep(2 ** (attempt - 1))

			except (httpx.RequestError, httpx.TimeoutException) as exc:
				print(f'[Button Template Attempt {attempt}] Request failed: {exc}')
				if attempt == retries:
					return {'error': str(exc)}
				await asyncio.sleep(2 ** (attempt - 1))


# Initialize the client
facebook = MessengerClient(settings.get('PAGE_ACCESS_TOKEN', ''))


# Example usage functions
async def example_usage():
	"""Example of how to use the enhanced Facebook Messenger client."""

	# Initialize client
	async with MessengerClient(page_access_token='YOUR_TOKEN') as client:
		recipient_id = 'USER_PSID'

		# Send text message
		await client.send_text_message(recipient_id, 'Hello! 👋')

		# Send image with text
		await client.send_image_with_text(
			fb_sender_id=recipient_id,
			image_url='https://example.com/image.jpg',
			text='Check out this cool image!',
		)

		# Send local image file
		await client.send_image_with_text(
			fb_sender_id=recipient_id,
			image_path='/path/to/local/image.jpg',
			text="Here's a local image!",
		)

		# Send quick replies
		quick_replies = [
			{'content_type': 'text', 'title': 'Yes', 'payload': 'yes'},
			{'content_type': 'text', 'title': 'No', 'payload': 'no'},
		]
		await client.send_quick_replies(
			recipient_id, 'Do you like this?', quick_replies
		)
