import csv
import io
import os
import logging
import xmlrpc.client
from lxml import etree
from meta_app_chatbot.config.settings import settings
from meta_app_chatbot.cache.cache import cache_register
from datetime import datetime, date
from langchain_core.tools import tool
from meta_app_chatbot.agent.utils import traceback, log_print
from typing import List, Dict, Any, Union


class OdooController:
    """
    Enhanced Odoo XML-RPC controller with comprehensive error handling,
    additional methods, and best practices implementation.
    """

    def __init__(self, url: str, db: str, username: str, password: str):
        """
        Initialize Odoo connection.

        Args:
            url: Odoo server URL (e.g., 'https://mycompany.odoo.com')
            db: Database name
            username: Username for authentication
            password: Password or API key for authentication

        Raises:
            ValueError: If authentication fails
            ConnectionError: If unable to connect to server
        """
        self.url = url.rstrip("/")
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        self.common = None
        self.models = None
        self.logger = logging.getLogger(__name__)

        try:
            # Initialize connection
            self._authenticate()
            self._setup_models_proxy()

        except Exception as e:
            self.logger.error(f"Failed to initialize Odoo connection: {e}")
        try:
            self.fields_key_type, self.fields_prompt = self.get_all_fields_with_type()
            # Set up logging
            self.models_name = [i for i in self.get_model_list() if "crm" in i]
        except Exception as e:
            self.fields_key_type, self.fields_prompt = {}, {}
            # Set up logging
            self.models_name = []
            self.logger.error(f"Failed to initialize Odoo connection: {e}")

    def get_all_fields_with_type(self):
        value_list = {}
        prompt_fields_list = {}
        type_change = {
            "boolean": bool,
            "char": str,
            "date": "date",
            "datetime": "datetime",
            "float": float,
            "integer": int,
            "many2many": str,
            "monetary": float,
            "one2many": int,
            "many2one": int,
            "selection": str,
            "text": str,
            "html": str,
        }
        # to get the fields that only appear in the form
        for key, value in self.fields_get(model="crm.lead").items():
            if key in ["id", "description", "name", "display_name", "stage_id"]:
                type_name = type_change.get(value.get("type"), str)
                desc = value["string"]
                help = value.get("help", "")
                value_list[key] = type_name
                if (
                    type_name not in ["date", "datetime"]
                    and type_name != "str"
                    and type_name != str
                ):
                    prompt_fields_list[key] = f"{type_name.__name__},{desc},{help}"

                else:
                    prompt_fields_list[key] = f"{type_name},{desc},{help}"

        for key, value in self.crm_fields_get(
            model="crm.lead", view_type="form", attributes=["string", "type", "help"]
        ).items():
            if "x_" in key or key in [
                "id",
                "description",
                "name",
                "display_name",
                "stage_id",
            ]:
                type_name = type_change.get(value.get("type"), str)
                desc = value["string"]
                help = value.get("help", "")
                value_list[key] = type_name
                if (
                    type_name not in ["date", "datetime"]
                    and type_name != "str"
                    and type_name != str
                ) or key in ["id", "description", "name", "display_name", "stage_id"]:
                    prompt_fields_list[key] = f"{type_name.__name__},{desc},{help}"
                elif type_name != "str" and type_name != str:
                    prompt_fields_list[key] = f"{type_name},{desc},{help}"
        # to get the fields that not appear in the form but still important like id

        return value_list, prompt_fields_list

    def _authenticate(self) -> None:
        """Authenticate with Odoo server."""
        try:
            self.common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")

            # Test connection first
            version_info = self.get_version()
            self.logger.info(
                f"Connected to Odoo {version_info.get('server_version', 'Unknown')}"
            )

            # Authenticate
            self.uid = self.common.authenticate(
                self.db, self.username, self.password, {}
            )
            if not self.uid:
                raise ValueError(
                    f"Authentication failed for user '{self.username}' on database '{self.db}'"
                )

            self.logger.info(f"Successfully authenticated as user ID: {self.uid}")

        except xmlrpc.client.Fault as e:
            raise ConnectionError(f"XML-RPC Fault: {e}")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to Odoo server: {e}")

    def _setup_models_proxy(self) -> None:
        """Set up the models proxy for executing operations."""
        try:
            self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")
        except Exception as e:
            raise ConnectionError(f"Failed to set up models proxy: {e}")

    def _execute_kw(
        self, model: str, method: str, args: List = None, kwargs: Dict = None
    ) -> Any:
        """
        Execute a method on an Odoo model with error handling.

        Args:
            model: Model name (e.g., 'res.partner')
            method: Method name (e.g., 'search', 'read', 'create')
            args: Positional arguments
            kwargs: Keyword arguments

        Returns:
            Result from the method execution

        Raises:
            xmlrpc.client.Fault: For Odoo-specific errors
            Exception: For other execution errors
        """
        args = args or []

        kwargs = kwargs or {}

        try:
            return self.models.execute_kw(
                self.db, self.uid, self.password, model, method, args, kwargs
            )
        except xmlrpc.client.Fault as e:
            self.logger.error(f"Odoo Fault in {model}.{method}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error executing {model}.{method}: {e}")
            raise

    def get_version(self) -> Dict[str, Any]:
        """
        Get Odoo server version information.

        Returns:
            Dictionary containing version information
        """
        try:
            return self.common.version()
        except Exception as e:
            self.logger.error(f"Failed to get version info: {e}")
            raise

    def search(
        self,
        model: str,
        domain: List = None,
        offset: int = 0,
        limit: int = 0,
        order: str = None,
    ) -> List[int]:
        """
        Search for records matching the domain.

        Args:
            model: Model name
            domain: Search domain (list of tuples)
            offset: Number of records to skip
            limit: Maximum number of records to return (0 = no limit)
            order: Sorting order (e.g., 'name desc')

        Returns:
            List of record IDs
        """
        domain = domain or []
        kwargs = {}

        if offset > 0:
            kwargs["offset"] = offset
        if limit > 0:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order

        return self._execute_kw(model, "search", [domain], kwargs)

    def search_count(self, model: str, domain: List = None) -> int:
        """
        Count records matching the domain.

        Args:
            model: Model name
            domain: Search domain (list of tuples)

        Returns:
            Number of matching records
        """
        domain = domain or []
        return self._execute_kw(model, "search_count", [domain])

    def read(
        self, model: str, ids: Union[int, List[int]], fields: List[str] = None
    ) -> List[Dict]:
        """
        Read records by ID.

        Args:
            model: Model name
            ids: Record ID or list of IDs
            fields: List of fields to read (None = all fields)

        Returns:
            List of record dictionaries
        """
        if isinstance(ids, int):
            ids = [ids]

        kwargs = {}
        if fields:
            kwargs["fields"] = fields

        return self._execute_kw(model, "read", [ids], kwargs)

    def search_read(
        self,
        model: str,
        domain: List = None,
        fields: List[str] = None,
        offset: int = 0,
        limit: int = 0,
        order: str = None,
    ) -> List[Dict]:
        """
        Search and read records in one call.

        Args:
            model: Model name
            domain: Search domain (list of tuples)
            fields: List of fields to read (None = all fields)
            offset: Number of records to skip
            limit: Maximum number of records to return (0 = no limit)
            order: Sorting order

        Returns:
            List of record dictionaries
        """
        domain = domain or []
        kwargs = {}

        if fields:
            kwargs["fields"] = fields
        if offset > 0:
            kwargs["offset"] = offset
        if limit > 0:
            kwargs["limit"] = limit
        if order:
            kwargs["order"] = order

        return self._execute_kw(model, "search_read", [domain], kwargs)

    def create(
        self, model: str, data: Union[Dict, List[Dict]]
    ) -> Union[int, List[int]]:
        """
        Create new record(s).

        Args:
            model: Model name
            data: Dictionary of field values or list of dictionaries

        Returns:
            Record ID or list of IDs for created records
        """
        if isinstance(data, dict):
            return self._execute_kw(model, "create", [data])
        else:
            # For multiple records, create them one by one
            ids = []
            for record_data in data:
                record_id = self._execute_kw(model, "create", [record_data])
                ids.append(record_id)
            return ids

    def write(self, model: str, ids: Union[int, List[int]], data: Dict) -> bool:
        """
        Update existing record(s).

        Args:
            model: Model name
            ids: Record ID or list of IDs to update
            data: Dictionary of field values to update

        Returns:
            True if successful
        """
        if isinstance(ids, int):
            ids = [ids]

        return self._execute_kw(model, "write", [ids, data])

    def unlink(self, model: str, ids: Union[int, List[int]]) -> bool:
        """
        Delete record(s).

        Args:
            model: Model name
            ids: Record ID or list of IDs to delete

        Returns:
            True if successful
        """
        if isinstance(ids, int):
            ids = [ids]

        return self._execute_kw(model, "unlink", [ids])

    def fields_get(
        self, model: str, fields: List[str] = None, attributes: List[str] = None
    ) -> Dict[str, Dict]:
        """
        Get field definitions for a model.

        Args:
            model: Model name
            fields: List of field names (None = all fields)
            attributes: List of attributes to return (e.g., ['string', 'type', 'help'])

        Returns:
            Dictionary of field definitions
        """
        args = []
        kwargs = {}

        if fields:
            args.append(fields)
        if attributes:
            kwargs["attributes"] = attributes

        return self._execute_kw(model, "fields_get", args, kwargs)

    def crm_fields_get(
        self,
        model: str,
        view_type: str = "form",
        fields: List[str] = None,
        attributes: List[str] = None,
    ) -> Dict[str, Dict]:
        """
        Retrieve metadata only for fields visible in the specified CRM view.

        Args:
            model (str): The model name (e.g., 'crm.lead').
            view_type (str): View type to check ('form', 'tree', etc.).
            fields (List[str], optional): Specific field names to include.
            attributes (List[str], optional): Field attribute keys to return (e.g. ['string','type','help']).

        Returns:
            Dict[field_name, Dict]: A dict of field metadata limited to the visible fields.
        """
        # 1️⃣ Get full field definitions
        field_defs = self._execute_kw(
            model, "fields_get", [fields or []], {"attributes": attributes or []}
        )

        # 2️⃣ Get view XML architecture
        view = self._execute_kw(model, "get_view", [], {"view_type": view_type})
        arch = view.get("arch") or ""
        doc = etree.XML(arch)

        # 3️⃣ Extract all field names present in the view
        view_fields = set()
        for node in doc.xpath("//field"):
            fname = node.get("name")
            if fname:
                view_fields.add(fname)

        # 4️⃣ Filter to only include visible fields
        filtered = {f: field_defs[f] for f in view_fields if f in field_defs}
        return filtered

    def name_get(self, model: str, ids: Union[int, List[int]]) -> List[tuple]:
        """
        Get display names for records.

        Args:
            model: Model name
            ids: Record ID or list of IDs

        Returns:
            List of tuples (id, display_name)
        """
        if isinstance(ids, int):
            ids = [ids]

        return self._execute_kw(model, "name_get", [ids])

    def name_search(
        self,
        model: str,
        name: str = "",
        domain: List = None,
        operator: str = "ilike",
        limit: int = 100,
    ) -> List[tuple]:
        """
        Search for records by name.

        Args:
            model: Model name
            name: Name to search for
            domain: Additional search domain
            operator: Search operator ('ilike', '=', etc.)
            limit: Maximum number of results

        Returns:
            List of tuples (id, display_name)
        """
        domain = domain or []
        kwargs = {"args": [name], "operator": operator, "context": {}, "limit": limit}

        if domain:
            kwargs["args"] = [name, domain]

        return self._execute_kw(model, "name_search", [], kwargs)

    async def _fetch_available_cities(self) -> set:
        """Fetches a set of available cities from Odoo."""
        try:
            if not cache_register.exists_auto("city"):
                city_data = odoo.search_read("crm.lead", fields=["x_studio_city"])
                city_list = list(
                    set(
                        data["x_studio_city"]
                        for data in city_data
                        if data.get("x_studio_city")
                    )
                )
                cache_register.set_auto(key="city", value=city_list)
            else:
                city_list = cache_register.get_auto(key="city")

            return city_list
        except Exception as e:
            log_print("Error", f"Error retrieving city list from Odoo: {e}")
            return set()

    def call_method(
        self, model: str, method: str, record_ids: List[int] = None, *args, **kwargs
    ) -> Any:
        """
        Call a custom method on a model.

        Args:
            model: Model name
            method: Method name
            record_ids: List of record IDs (for record methods)
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Returns:
            Method result
        """
        call_args = []
        if record_ids:
            call_args.append(record_ids)
        call_args.extend(args)

        return self._execute_kw(model, method, call_args, kwargs)

    def get_metadata(self, model: str, ids: Union[int, List[int]]) -> List[Dict]:
        """
        Get metadata for records (creation/modification dates, user, etc.).

        Args:
            model: Model name
            ids: Record ID or list of IDs

        Returns:
            List of metadata dictionaries
        """
        if isinstance(ids, int):
            ids = [ids]

        return self._execute_kw(model, "get_metadata", [ids])

    def export_data(self, model: str, ids: List[int], fields: List[str]) -> Dict:
        """
        Export data from records.

        Args:
            model: Model name
            ids: List of record IDs to export
            fields: List of field names to export

        Returns:
            Dictionary containing exported data
        """
        return self._execute_kw(model, "export_data", [ids, fields])

    def check_access_rights(
        self, model: str, operation: str, raise_exception: bool = True
    ) -> bool:
        """
        Check if current user has access rights for an operation.

        Args:
            model: Model name
            operation: Operation ('read', 'write', 'create', 'unlink')
            raise_exception: Whether to raise exception if no access

        Returns:
            True if access is granted
        """
        return self._execute_kw(
            model,
            "check_access_rights",
            [operation],
            {"raise_exception": raise_exception},
        )

    def get_model_list(self) -> List[str]:
        """
        Get list of all available models.

        Returns:
            List of model names
        """
        models = self.search_read("ir.model", fields=["model"], order="model")
        return [model["model"] for model in models]

    def test_connection(self) -> bool:
        """
        Test if the connection is still valid.

        Returns:
            True if connection is valid
        """
        try:
            self.get_version()
            return True
        except Exception as e:
            self.logger.warning(f"Connection test failed: {e}")
            return False

    def extract_crm_lead_info_as_csv(self, leads):
        if not leads:
            return ""

        # Pick only the most valuable fields
        fields = self.fields_key_type.keys()
        # Create CSV in-memory
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(fields)

        # Write rows
        for lead in leads:
            row = []
            for field in fields:
                value = lead.get(field)
                if value:
                    if isinstance(value, list):
                        # Most Odoo fields like [id, name] -> take the name
                        value = value[1] if len(value) > 1 else value[0]
                    elif isinstance(value, str):
                        value = value.strip()
                    row.append(value)
                else:
                    row.append(value)

            writer.writerow(row)

        return output.getvalue()

    def convert_value(self, field_type, value):
        if isinstance(value, list):
            final_output = []
            for item in value:
                final_output.append(self.convert_value(field_type, item))
            return final_output
        # Normalize field_type to string if it's a type
        if isinstance(field_type, type):
            field_type = field_type.__name__
        try:
            if field_type == "bool":
                return bool(value)
            elif field_type == "float":
                return float(value)
            elif field_type == "int":
                return int(value)
            elif field_type == "list":
                return list(value) if isinstance(value, (list, tuple, set)) else [value]
            elif field_type == "str":
                return str(value)
            elif field_type == "date":
                if isinstance(value, date):
                    return value.strftime("%Y-%m-%d")
                elif isinstance(value, str):
                    parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
                    return parsed_date.strftime("%Y-%m-%d")
                return (
                    datetime.strptime(str(value), "%Y-%m-%d")
                    .date()
                    .strftime("%Y-%m-%d")
                )
            elif field_type == "datetime":
                if isinstance(value, datetime):
                    return value.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(value, str):
                    try:
                        parsed_datetime = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        parsed_datetime = datetime.strptime(value, "%Y-%m-%d")
                    return parsed_datetime.strftime("%Y-%m-%d %H:%M:%S")
                return datetime.strptime(str(value), "%Y-%m-%d").strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            return value
        except Exception as e:
            logging.exception(
                f"Failed to convert value '{value}' for field_type '{field_type}': {e}"
            )
            return value  # fallback

    def change_value(self, d):
        """
        Expects a list or tuple like ['int', '123']
        Will convert '123' to int and return it
        """
        try:
            field_type = self.fields_key_type[d[0]]
            value = d[-1]
            converted = self.convert_value(field_type, value)
            d[-1] = converted
            d[0] = d[0].strip().lower()
            d[1] = d[1].strip().lower()
        except Exception as e:
            print(e)
            d = []
        return d


# Example usage and helper functions
class OdooHelper:
    """Helper class with commonly used operations."""

    def __init__(self, odoo_controller: OdooController):
        self.odoo = odoo_controller

    def get_user_info(self, user_id: int = None) -> Dict:
        """Get current or specified user information."""
        uid = user_id or self.odoo.uid
        users = self.odoo.read(
            "res.users", uid, ["name", "login", "email", "groups_id"]
        )
        return users[0] if users else {}

    def get_company_info(self) -> Dict:
        """Get current user's company information."""
        user = self.get_user_info()
        if "company_id" in user:
            company_id = user["company_id"][0]
            companies = self.odoo.read("res.company", company_id)
            return companies[0] if companies else {}
        return {}

    def search_partners_by_email(self, email: str) -> list[dict]:
        """Search partners by email address."""
        domain = [("email", "=", email)]
        return self.odoo.search_read("res.partner", domain)

    def create_contact(
        self, name: str, email: str = None, phone: str = None, is_company: bool = False
    ) -> int:
        """Create a new contact."""
        data = {"name": name, "is_company": is_company}
        if email:
            data["email"] = email
        if phone:
            data["phone"] = phone

        return self.odoo.create("res.partner", data)


odoo = OdooController(
    settings.get("odoo_url"),
    settings.get("odoo_db"),
    settings.get("odoo_email"),
    settings.get("odoo_password"),
)


@tool
def read_data_by_reveal_id(reveal_id: str = "") -> dict:
    """
    Retrieve CRM lead data by reveal ID and return it in CSV format.

    Description:
        This tool searches the Odoo CRM system for a lead whose 'reveal_id' matches the provided ID.
        It extracts the most relevant information and returns it as a CSV-formatted string.
        Useful when the user references a specific request or inquiry by ID.

    Args:
        reveal_id (str): The unique reveal ID associated with the CRM lead.

    Returns:
        dict: A structured dictionary with:
            - success (bool): Indicates whether the data was retrieved successfully.
            - content (str): CSV string containing the extracted lead information (empty if failed).
            - error (str): Error message if the operation fails.
            - args (dict): Original input arguments for traceability.
    """
    try:
        # Search for CRM leads by reveal_id
        log_print("info", "start read_data_by_reveal_id")
        leads = odoo.search_read("crm.lead", domain=[["reveal_id", "=", reveal_id]])

        # Extract and format the data into CSV
        data = odoo.extract_crm_lead_info_as_csv(leads)

        if not data:
            return {
                "success": False,
                "content": "",
                "error": "No data found for the provided reveal ID.",
                "args": {"id": id},
            }
        log_print("info", "end read_data_by_reveal_id")

        return {"success": True, "content": data, "error": "", "args": {"id": id}}

    except Exception as e:
        return {"success": False, "content": "", "error": str(e), "args": {"id": id}}


@tool
async def get_all_free_apartments(area: str | Any = "") -> dict:
    """
    Retrieve all available (free) apartments for user selection.
    Args:
        area (optional) (str) area of search leave it empty string for getting all results
    Description:
        This tool queries the Odoo CRM system for leads that are currently in the "free apartment" stage
        (typically represented by a `stage_id` of 0). It compiles a list of all such entries and returns
        them in a CSV-formatted string.

    Returns:
        dict: A structured dictionary containing:
            - success (bool): True if data retrieval was successful, False otherwise.
            - content (str): A CSV-formatted string with apartment information (empty on failure).
            - error (str): A descriptive error message if the operation fails.
            - args (dict): Additional context (currently empty for traceability).
    """
    try:
        log_print("info", "start get_all_free_apartments tool")
        area = area or ""
        # Retrieve leads marked as 'free apartments'
        leads = odoo.search_read(
            "crm.lead", domain=[["stage_id", "=", 1], ["city", "ilike", area]]
        )

        # Convert lead data to CSV format
        csv_data = odoo.extract_crm_lead_info_as_csv(leads)

        if not csv_data:
            return {
                "success": False,
                "content": "",
                "error": "No free apartments found.",
                "args": {"area": area},
            }
        log_print("info", "end get_all_free_apartments tool")

        return {
            "success": True,
            "content": csv_data,
            "error": "",
            "args": {"area": area},
        }

    except Exception as e:
        log_print("error", f"Error extracting facts: {e} {traceback.format_exc()}")
        return {
            "success": False,
            "content": "",
            "error": f"Error retrieving apartments: {str(e)}",
            "args": {"area": area},
        }


async def update_states(id, stage_id: str, info) -> dict:
    """
    update data of apartment
    Args:
        id (str) id of apartment
        info (dict) information that you want update
    Description:
        This tool queries the Odoo CRM system for leads that are currently in the "free apartment" stage
        (typically represented by a `stage_id` of 0). It compiles a list of all such entries and returns
        them in a CSV-formatted string.

    Returns:
        dict: A structured dictionary containing:
            - success (bool): True if data retrieval was successful, False otherwise.
            - content (str): A CSV-formatted string with apartment information (empty on failure).
            - error (str): A descriptive error message if the operation fails.
            - args (dict): Additional context (currently empty for traceability).
    """
    try:
        # Retrieve leads marked as 'free apartments'
        state = odoo.write("crm.lead", ids=id, data={"stage_id": stage_id, **info})
        if not state:
            return {
                "success": False,
                "content": "",
                "error": "No free apartments found.",
                "args": {"id": id, "info": info},
            }

        return {
            "success": True,
            "content": "",
            "error": "",
            "args": {"id": id, "info": info},
        }

    except Exception as e:
        return {
            "success": False,
            "content": "",
            "error": f"Error retrieving apartments: {str(e)}",
            "args": {"id": id, "info": info},
        }


@tool
async def get_specifc_apartment_by_id(id: str = "") -> dict:
    """
    Retrieve CRM lead data by  ID of apartment and return it in CSV format.

    Description:
        This tool searches the Odoo CRM system for a lead whose 'reveal_id' matches the provided ID.
        It extracts the most relevant information and returns it as a CSV-formatted string.
        Useful when the user references a specific request or inquiry by ID.

    Args:
        reveal_id (str): The unique reveal ID associated with the CRM lead.

    Returns:
        dict: A structured dictionary with:
            - success (bool): Indicates whether the data was retrieved successfully.
            - content (str): CSV string containing the extracted lead information (empty if failed).
            - error (str): Error message if the operation fails.
            - args (dict): Original input arguments for traceability.
    """
    try:
        log_print("info", "start get_specifc_apartment_by_id tool")

        # Search for CRM leads by reveal_id
        leads = odoo.search_read("crm.lead", domain=[["id", "=", id]])

        # Extract and format the data into CSV
        data = odoo.extract_crm_lead_info_as_csv(leads)

        if not data:
            return {
                "success": False,
                "content": "",
                "error": "No data found for the provided reveal ID.",
                "args": {"id": id},
            }

        return {"success": True, "content": data, "error": "", "args": {"id": id}}

    except Exception as e:
        log_print("error", f"Error extracting facts: {e} {traceback.format_exc()}")

        return {"success": False, "content": "", "error": str(e), "args": {"id": id}}


#
