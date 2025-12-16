import re
import requests
import logging
import json # Added import
import mimetypes # Add mimetypes for image processing
import base64 # Add base64 for image processing
from datetime import datetime
from typing import Union

logger = logging.getLogger(__name__)

# This constant is now used only here.
CUSTOMERS_API_URL = "http://127.0.0.1:8000/api/search_customer/"

def search_customer_by_name(name: str) -> dict:
    """Searches for a customer by name via the new API endpoint."""
    logger.info(f"Searching for customer '{name}' via API...")
    try:
        search_url = f"{CUSTOMERS_API_URL}?name={name}"
        response = requests.get(search_url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API error while searching for customer '{name}': {e}")
        return {}

def to_ordinal(n):
    """Converts an integer to its ordinal string form (e.g., 1 -> 1st, 2 -> 2nd)."""
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    return str(n) + suffix

def get_display_value(value, is_price=False):
    """Returns 'N/A' for empty/zero values, otherwise the value itself."""
    if not value:
        return "N/A"
    if is_price:
        try:
            return f"RM {float(value):.2f}"
        except (ValueError, TypeError):
            return str(value)
    return str(value)

def get_gl_code_for_service(service_description: str) -> str:
    """Returns the correct GL code based on the service description."""
    from services_config import GL_CODE_MAPPING # Import here to avoid circular dependency with logic.py
    desc = service_description.lower()
    for keyword, gl_code in GL_CODE_MAPPING.items():
        if keyword in desc:
            return gl_code
    # Default GL code for any unmatched service
    return "501-000"

def validate_truck_number(truck_number: str) -> tuple[bool, str]:
    """Validate truck number format."""
    if not truck_number or len(truck_number.strip()) == 0:
        return False, "Truck number cannot be empty."
    truck_number = truck_number.strip().upper()
    if len(truck_number) < 3 or len(truck_number) > 15:
        return False, "Truck number must be between 3 and 15 characters."
    if not re.match(r'^[A-Z0-9\s\-]+$', truck_number):
        return False, "Truck number can only contain letters, numbers, spaces, and dashes."
    return True, ""

def validate_phone_number(phone: str) -> tuple[bool, str]:
    """
    Validate Malaysian phone number, allowing for empty inputs.
    Returns: (is_valid, error_message)
    """
    if not phone:
        return False, "Phone number cannot be empty."

    # Allow "N/A", "NA", or "0" as valid empty inputs
    if phone.strip().upper() in ["N/A", "NA", "0"]:
        return True, ""
    
    phone = re.sub(r'[\s\-()]', '', phone) # Remove common separators
    
    # Malaysian phone: 01X-XXXXXXX or 01X-XXXXXXXX (10-11 digits starting with 01)
    if not re.match(r'^(01|\+?601)[0-9]{8,9}$', phone):
        return False, "Please enter a valid Malaysian phone number (e.g., 012-3456789 or +6012-3456789)."
    return True, ""

def validate_price(price_str: str) -> tuple[bool, float, str]:
    """Validate and parse price input."""
    try:
        price = float(price_str)
        if price < 0:
            return False, 0.0, "Price cannot be negative."
        if price > 10_000_000:
            return False, 0.0, "Price seems unreasonably high. Please check."
        return True, price, ""
    except ValueError:
        return False, 0.0, "Please enter a valid number for the price."

def safe_json_loads(raw_json_string: str) -> dict:
    """
    Safely loads a JSON string, handling potential JSONDecodeError.
    Returns an empty dictionary on error.
    """
    try:
        return json.loads(raw_json_string)
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON from AI: {raw_json_string}")
        return {}

def parse_line_items_from_text(text: str) -> list[dict]:
    """
    Parses a multi-line string of line items into a list of dictionaries.
    More precise version to avoid including price in description.
    """
    lines = text.strip().split('\n')
    parsed_items = []
    default_gl_code = "501-000"

    # Regex to capture:
    # 1. (Optional) Quantity and multiplier (e.g., "2 unit", "2x")
    # 2. The description text
    # 3. (Optional) "RM" prefix
    # 4. The price
    item_regex = re.compile(
        r'^\s*(?:(\d+)\s*(?:pcs?|unit|units|x|X)?)?\s*(.*?)\s*(?:RM)?\s*([\d,]+\.?\d*)\s*$', 
        re.IGNORECASE
    )

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = item_regex.match(line)
        if match:
            qty_str, description, price_str = match.groups()
            
            qty = int(qty_str) if qty_str else 1
            unit_price = float(price_str.replace(',', ''))
            description = description.strip()

            # Clean up dangling hyphens or colons from the description
            if description.endswith((':', '-')):
                description = description[:-1].strip()

            parsed_items.append({
                "line_description": description if description else "Item",
                "unit_price": unit_price,
                "qty": qty,
                "gl_code": default_gl_code
            })
        else:
            # Fallback for lines that don't match, e.g., just a description
            # This part is less critical if the format is consistent
            parsed_items.append({
                "line_description": line,
                "unit_price": 0.0,
                "qty": 1,
                "gl_code": default_gl_code
            })

    return parsed_items

def validate_date(date_string: str) -> (bool, Union[datetime.date, str, None]):
    """Validates if a string is a valid date in YYYY-MM-DD format."""
    try:
        return True, datetime.strptime(date_string, '%Y-%m-%d').date(), ""
    except ValueError:
        return False, None, "Invalid date format. Please use YYYY-MM-DD."