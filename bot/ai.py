import google.generativeai as genai
import os
import logging
import PIL.Image
import json

logger = logging.getLogger(__name__)

# Configure the Gemini API key
try:
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
except KeyError:
    logger.error("GEMINI_API_KEY environment variable not set.")
    # You might want to handle this more gracefully, e.g., by disabling AI features
    # and logging a clear error message for the user.
    raise ImportError("GEMINI_API_KEY not set, cannot use AI features.")


async def extract_details_from_text(text: str) -> dict:
    """
    Uses the Gemini API to extract details from the user's text.

    Args:
        text: The user's input text.

    Returns:
        A dictionary of extracted details.
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = f"""
    Extract the following details from the text below:
    - truck_number
    - company_name
    - company_address
    - cust_contact
    - body
    - salesperson
    - line_items (with description, quantity, and unit_price)

    Text:
    {text}

    Return the extracted details in JSON format.
    """
    try:
        response = await model.generate_content_async(prompt)
        # It's better to load the JSON here to handle potential errors
        return json.loads(response.text)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error calling Gemini API or parsing JSON: {e}")
        return {}


async def extract_text_from_image(image: PIL.Image.Image) -> str:
    """
    Uses the Gemini API to extract text from an image.

    Args:
        image: The image to extract text from.

    Returns:
        The extracted text.
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    try:
        response = await model.generate_content_async(image)
        return response.text
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}")
        return ""


async def extract_line_items_from_text(text: str) -> list:
    """
    Uses the Gemini API to extract line items from the user's text.

    Args:
        text: The user's input text for line items.

    Returns:
        A list of dictionaries, where each dictionary is a line item.
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = f"""
    Extract the line items from the text below. Each item should have a 'description', 'qty', and 'unit_price'.
    If quantity is not mentioned, assume it is 1.
    If a line does not contain a price, it is not a line item and should be ignored.
    The output MUST be a valid JSON list of objects. Each object in the list MUST contain 'description', 'qty', and 'unit_price' keys.

    Text:
    {text}

    Return a valid JSON list of objects. For example:
    [
        {{"description": "New Lorry", "qty": 1, "unit_price": 150000}},
        {{"description": "Service B", "qty": 2, "unit_price": 250}}
    ]
    """
    try:
        response = await model.generate_content_async(prompt)
        # Clean the response to ensure it's valid JSON
        cleaned_response = (
            response.text.strip().replace("```json", "").replace("```", "").strip()
        )
        return json.loads(cleaned_response)
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"Error in extract_line_items_from_text: {e}")
        return []
