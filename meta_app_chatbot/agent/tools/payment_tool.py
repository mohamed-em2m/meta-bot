import datetime
import json
import traceback
import uuid

from langchain_core.tools import tool

from meta_app_chatbot.agent.utils import generate_access_key, log_print
from meta_app_chatbot.config.settings import settings
from meta_app_chatbot.db.firestore import FirestoreFactory

from .odoo_tools import odoo


@tool
async def create_payment_and_booking(
    apartment_id: int,
    name: str,
    phone: str,
    email: str,
    address: str,
    additions: dict = None,
) -> dict:
    """
    Creates a booking and payment record if the apartment (crm.lead) is available (stage_id == 0).
    Stores booking info in local DB and updates the crm.lead stage and user info in Odoo.

    Args:
        apartment_id (int): The ID of the apartment which user want book.
        name (str): Customer name.
        phone (str): Customer phone.
        email (str): Customer email.
        address (str): Customer address.
        additions (dict, optional): Additional info such as 'source' and 'id'.

    Returns:
        dict: Result with success status, content, error message, and args.
    """
    log_print("info", "start create_payment_and_booking tool")

    if additions is None:
        additions = {}

    try:
        if not all([apartment_id, name, phone, email, address]):
            return {
                "success": False,
                "content": "",
                "error": "All fields are required: apartment_id, name, phone, email, address.",
                "args": {
                    "apartment_id": apartment_id,
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "address": address,
                },
            }

        info = odoo.search_read("crm.lead", domain=[["id", "=", apartment_id]])

        if not info:
            return {
                "success": False,
                "content": "",
                "error": f"No apartment found with id {apartment_id}",
                "args": {
                    "apartment_id": apartment_id,
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "address": address,
                },
            }

        lead = info[0]
        log_print("info", f"id {apartment_id} with {lead.get('stage_id')[0]}")

        # Check if the apartment is available (stage_id == 0)
        if lead.get("stage_id")[0] == 1:
            now = datetime.datetime.now()
            deadline = now + datetime.timedelta(hours=6)
            reveal_id = f"{apartment_id}" + generate_access_key() + "_em"

            payload = {
                "name": name,
                "phone": phone,
                "email": email,
                "address": address,
                "source": additions.get("source"),
                "id": additions.get("firestore_id"),
                "deadline": deadline.isoformat(),
                "start_time": now.isoformat(),
                "apartment_id": apartment_id,
                "reveal_id": reveal_id,
            }

            # Store booking info in local DB

            # Prepare user info JSON for Odoo custom field

            user_info = json.dumps(
                {
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "address": address,
                    "source": additions.get("source"),
                    "id": additions.get("firestore_id"),
                }
            )

            await FirestoreFactory.get(
                settings.get("DEFAULT_BILLING_POOL_DB_NAME")
            ).store(additions["firestore_id"], f"{reveal_id}", [payload])

            # Update the crm.lead record stage and user info
            odoo.write(
                "crm.lead",
                ids=apartment_id,
                data={
                    "stage_id": 2,
                    "x_studio_user_info": user_info,
                    "reveal_id": reveal_id,
                },
            )
            log_print("info", "end create_payment_and_booking tool")

            return {
                "success": True,
                "content": {"reveal_id": reveal_id, "fawary_id": 232002},
                "error": "",
                "args": {
                    "apartment_id": apartment_id,
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "address": address,
                },
            }

        else:
            return {
                "success": False,
                "content": "",
                "error": "Sorry, the apartment is not available",
                "args": {
                    "apartment_id": apartment_id,
                    "name": name,
                    "phone": phone,
                    "email": email,
                    "address": address,
                },
            }

    except Exception as e:
        log_print("error", f"{e} {traceback.format_exc()}")
        return {
            "success": False,
            "content": "",
            "error": f"Exception occurred: {str(e)}",
            "args": {
                "apartment_id": apartment_id,
                "name": name,
                "phone": phone,
                "email": email,
                "address": address,
            },
        }


@tool
async def delete_payment_and_booking(reveal_id: str, additions: dict = None) -> dict:
    """
    Deletes a booking and payment record if it exists for the given apartment (crm.lead).
    Removes booking info from the local DB and resets the crm.lead stage and user info in Odoo.

    Args:
        reveal_id (str): The reveal_id of the apartment .
        additions (dict, optional): Additional metadata such as 'source' and 'id' you must not pass this infroamtion it will pass autmaticly.

    Returns:
        dict: Result with success status, content, error message, and args.
    """
    log_print("info", "start delete_payment_and_booking tool")

    if additions is None:
        additions = {}

    try:
        print(additions["firestore_id"], f"{reveal_id}")

        # Fetch the crm.lead record info by apartment_id
        info = odoo.search_read("crm.lead", domain=[["reveal_id", "=", reveal_id]])

        if not info:
            log_print(
                "info",
                f"The apartment {reveal_id} is not booked or already deleted or aleardy booked. info error",
            )

            return {
                "success": False,
                "content": "",
                "error": f"No apartment found with reveal_id  {reveal_id}",
                "args": {"reveal_id": reveal_id},
            }

        lead = info[0]

        # Only delete booking if stage_id is 2 (booked)
        if lead.get("stage_id")[0] == 2:
            # Remove booking info from local DB
            table = FirestoreFactory.get(settings.get("DEFAULT_BILLING_POOL_DB_NAME"))

            exist = await table.delete_certain_document(
                additions["firestore_id"], f"{reveal_id}"
            )
            if not exist:
                log_print("error", f"Failed to delete booking info for {reveal_id}")
                return {
                    "success": False,
                    "content": "",
                    "error": "you must use same account you used for booking to be able to delete it",
                    "args": {"reveal_id": reveal_id},
                }
            # Reset stage and clear user info in Odoo
            odoo.write(
                "crm.lead",
                ids=lead.get("id"),
                data={
                    "stage_id": 1,
                    "x_studio_user_info": "",
                    "reveal_id": f"{uuid.uuid4().hex[:20]}_{generate_access_key()}",
                },
            )

            log_print("info", "end delete_payment_and_booking tool")
            return {
                "success": True,
                "content": f"Payment and booking for apartment {reveal_id} deleted.",
                "error": "",
                "args": {"reveal_id": reveal_id},
            }

        else:
            log_print(
                "info",
                f"The apartment {reveal_id} is not booked or already deleted or aleardy booked. stage error",
            )

            return {
                "success": False,
                "content": "",
                "error": "The apartment is not booked or already deleted or aleardy booked.",
                "args": {"apartment_id": reveal_id},
            }

    except Exception as e:
        log_print("error", f"{e} {traceback.format_exc()}")
        return {
            "success": False,
            "content": "",
            "error": f"Exception occurred: {str(e)}",
            "args": {"apartment_id": reveal_id},
        }
