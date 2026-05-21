import traceback

from langchain_core.tools import tool

from meta_app_chatbot.agent.utils import log_print

from .odoo_controller import odoo
from .sql_to_domain_odoo import sql_to_odoo_domain


@tool
async def crm_reader(qeury: str) -> dict:
    """
    Retrieve CRM lead data from the Odoo system based on filtering criteria and return it in CSV format.
    This tool searches the Odoo CRM system using the provided `qeury` .
    Args:
        qeury :a sql query to search on

    Returns:
        dict: A response object with the following structure:
            - success (bool): Whether the data was retrieved successfully.
            - content (str): A CSV string containing the extracted lead data (empty if no leads were found).
            - error (str): Error message if the operation fails or no data is found.
            - args (dict): The original input arguments (`domain` and `fields`) for traceability.
    """
    try:
        log_print("info", "Starting crm_reader tool")

        # Query CRM leads from Odoo using domain and fields
        new_domain = []
        domain = sql_to_odoo_domain(qeury)
        domain = sorted(
            domain, key=lambda x: isinstance(x, list) and len(x) > 1 and x[1] == "in"
        )
        for d in domain:
            if d[0] in odoo.fields_key_type:
                log_print("info", f"change type of {d[0]}")

                new_d = odoo.change_value(d)
                if odoo.fields_key_type[new_d[0]] is str:
                    if isinstance(new_d[-1], list) and len(new_d[-1]) > 1:
                        new_domain.append("|")
                        for item in new_d[-1]:
                            new_domain += [[new_d[0], "ilike", item]]
                        if [new_d[0], "ilike", ""] not in new_domain:
                            new_domain += [[new_d[0], "ilike", ""]]

                    elif isinstance(new_d[-1], list):
                        new_domain.append("|")

                        new_domain += [[new_d[0], "ilike", new_d[-1][-1]]]
                        new_domain += [[new_d[0], "ilike", ""]]

                    else:
                        new_domain.append(odoo.change_value(new_d))
                else:
                    if isinstance(new_d[-1], list) and len(new_d[-1]) > 1:
                        new_domain.append("|")
                        for item in new_d[-1]:
                            new_domain += [[new_d[0], "=", item]]
                        if [new_d[0], "=", ""] not in new_domain:
                            new_domain += [[new_d[0], "=", ""]]

                    elif isinstance(new_d[-1], list):
                        new_domain += [[new_d[0], "=", new_d[-1][-1]]]

                    else:
                        new_domain.append(odoo.change_value(new_d))
        print(new_domain)
        leads = odoo.search_read("crm.lead", domain=new_domain)

        # Convert lead data into CSV format
        data = odoo.extract_crm_lead_info_as_csv(leads)

        if not data:
            return {
                "success": False,
                "content": "",
                "error": "No data found for the provided filters. try modify the parmeters",
                "args": {"domain": domain},
            }

        return {
            "success": True,
            "content": data,
            "error": "",
            "args": {"domain": domain},
        }

    except Exception as e:
        log_print("error", f"Error in crm_reader: {e} {traceback.format_exc()}")

        return {
            "success": False,
            "content": "",
            "error": f"{str(e)}  try modify the parmeters",
            "args": {"domain": domain},
        }
