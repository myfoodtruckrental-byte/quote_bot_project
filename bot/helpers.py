import re
import httpx  # Changed from requests
import logging
import json
import mimetypes
import base64
from datetime import datetime
from typing import Union

logger = logging.getLogger(__name__)

CUSTOMERS_API_URL = "http://127.0.0.1:8000/api/search_customer/"


async def search_customer_by_name(name: str) -> dict:
    """Searches for a customer by name via the new API endpoint asynchronously."""
    logger.info(f"Searching for customer '{name}' via API...")
    try:
        search_url = f"{CUSTOMERS_API_URL}?name={name}"
        async with httpx.AsyncClient() as client:
            response = await client.get(search_url, timeout=30)
            response.raise_for_status()
            return response.json()
    except httpx.RequestError as e:
        logger.error(f"API error while searching for customer '{name}': {e}")
        return {}


def to_ordinal(n):
    """Converts an integer to its ordinal string form (e.g., 1 -> 1st, 2 -> 2nd)."""
    if 11 <= (n % 100) <= 13:
        suffix = "th"
    else:
        suffix = ["th", "st", "nd", "rd", "th"][min(n % 10, 4)]
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
    from services_config import (
        GL_CODE_MAPPING,
    )  # Import here to avoid circular dependency with logic.py

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
    if not re.match(r"^[A-Z0-9\s\-]+", truck_number):
        return (
            False,
            "Truck number can only contain letters, numbers, spaces, and dashes.",
        )
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

    phone = re.sub(r"[\s\-()]", "", phone)  # Remove common separators

    # Malaysian phone: 01X-XXXXXXX or 01X-XXXXXXXX (10-11 digits starting with 01)
    if not re.match(r"^(01|\+?601)[0-9]{8,9}$", phone):
        return (
            False,
            "Please enter a valid Malaysian phone number (e.g., 012-3456789 or +6012-3456789).",
        )
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
    This version is more robust and handles more formats.
    """
    lines = text.strip().split("\n")
    parsed_items = []

    # Regex to find the price at the end of the string.
    # It can be preceded by "RM" and can have commas.
    price_regex = re.compile(r"(?:RM\s*)?([\d,]+\.?\d*)\s*$")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        price_match = price_regex.search(line)
        if not price_match:
            continue

        price_str = price_match.group(1)
        unit_price = float(price_str.replace(",", ""))

        # Get the part of the string before the price
        description_part = line[: price_match.start()].strip()

        # Regex to find quantity and units
        qty = 1
        description = description_part

        # Regex for quantity (e.g., "2 x", "2pcs", "2 units")
        qty_match = re.match(
            r"^\s*(\d+)\s*(x|pcs?|pc|unit|units)\s*", description_part, re.IGNORECASE
        )
        if qty_match:
            qty = int(qty_match.group(1))
            description = description_part[qty_match.end() :].strip()

        # Clean up the description
        description = description.strip(" ,-:")

        parsed_items.append(
            {
                "line_description": description if description else "Item",
                "unit_price": unit_price
                / qty,  # AI will give total price, so we divide by quantity
                "qty": qty,
                "gl_code": get_gl_code_for_service(description),
            }
        )

    return parsed_items


def validate_date(date_string: str) -> tuple[bool, Union[datetime.date, None], str]:
    """Validates if a string is a valid date in supported formats."""
    formats = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"]
    for fmt in formats:
        try:
            return True, datetime.strptime(date_string, fmt).date(), ""
        except ValueError:
            continue
    return (
        False,
        None,
        "Invalid date format. Please use YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY, or DD.MM.YYYY.",
    )
