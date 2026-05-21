from langchain.tools import tool
from typing import Any, Dict, Optional
from .facebook_messenger_controller import facebook


@tool
async def send_facebook_attachment(
    attachment_type: str = "image",
    url: str = "",
    file_path: str = "",
    additions: Dict[str, Any] = {},
) -> Dict[str, Any]:
    """
    Send an attachment (image, video, audio, or file) via Facebook Messenger.

    Args:
        attachment_type: Type of attachment ("image", "video", "audio", or "file").
        url: URL of the attachment (either this or file_path required).
        file_path: Local path to attachment file (either this or url required).
        additions: Dictionary containing additional data, must include 'fb_sender_id'.

    Returns:
        A dict with 'success': bool, 'response': raw API response, and 'error' if any.
    """
    fb_sender_id: Optional[str] = additions.get("fb_sender_id")

    if not fb_sender_id:
        return {
            "success": False,
            "error": "Missing 'fb_sender_id' in additions.",
            "response": None,
        }

    if not url and not file_path:
        return {
            "success": False,
            "error": "Either 'url' or 'file_path' must be provided.",
            "response": None,
        }

    if attachment_type not in ["image", "video", "audio", "file"]:
        return {
            "success": False,
            "error": "attachment_type must be 'image', 'video', 'audio', or 'file'.",
            "response": None,
        }

    try:
        async with facebook as client:
            response = await client.send_attachment(
                fb_sender_id=fb_sender_id,
                attachment_type=attachment_type,
                url=url if url else None,
                file_path=file_path if file_path else None,
            )

            return {
                "success": not response.get("error"),
                "response": response,
                "error": response.get("error") if response.get("error") else None,
            }
    except Exception as e:
        return {"success": False, "response": None, "error": str(e)}


@tool
async def send_facebook_image_with_text(
    image_url: str = "",
    image_path: str = "",
    text: str = "",
    additions: Dict[str, Any] = {},
) -> Dict[str, Any]:
    """
    Send an image with optional text via Facebook Messenger.

    Args:
        image_url: URL of the image to send (either this or image_path required).
        image_path: Local path to image file (either this or image_url required).
        text: Optional text message to send with the image.
        additions: Dictionary containing additional data, must include 'fb_sender_id'.

    Returns:
        A dict with 'success': bool, 'response': raw API response, and 'error' if any.
    """
    fb_sender_id: Optional[str] = additions.get("fb_sender_id")

    if not fb_sender_id:
        return {
            "success": False,
            "error": "Missing 'fb_sender_id' in additions.",
            "response": None,
        }

    if not image_url and not image_path:
        return {
            "success": False,
            "error": "Either 'image_url' or 'image_path' must be provided.",
            "response": None,
        }

    try:
        async with facebook as client:
            response = await client.send_image_with_text(
                fb_sender_id=fb_sender_id,
                image_url=image_url if image_url else None,
                image_path=image_path if image_path else None,
                text=text if text else None,
                reuse_attachment=True,
            )

            return {
                "success": not response.get("error"),
                "response": response,
                "error": response.get("error") if response.get("error") else None,
            }
    except Exception as e:
        return {"success": False, "response": None, "error": str(e)}


@tool
async def send_facebook_message(
    message: str = "", additions: Dict[str, Any] = {}
) -> Dict[str, Any]:
    """
    Send a text message via Facebook Messenger.

    Args:
        message: The message text to send.
        additions: Dictionary containing additional data, must include 'fb_sender_id'.

    Returns:
        A dict with 'success': bool, 'response': raw API response, and 'error' if any.
    """
    fb_sender_id: Optional[str] = additions.get("fb_sender_id")

    if not fb_sender_id:
        return {
            "success": False,
            "error": "Missing 'fb_sender_id' in additions.",
            "response": None,
        }

    if not message.strip():
        return {"success": False, "error": "Message cannot be empty.", "response": None}

    try:
        async with facebook as client:
            response = await client.send_text_message(
                fb_sender_id=fb_sender_id, text=message
            )
            return {
                "success": not response.get("error"),
                "response": response,
                "error": response.get("error") if response.get("error") else None,
            }
    except Exception as e:
        return {"success": False, "response": None, "error": str(e)}
