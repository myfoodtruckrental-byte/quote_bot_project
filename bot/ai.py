import logging
import json
import PIL.Image
import google.generativeai as genai

from .helpers import safe_json_loads # Import safe_json_loads

logger = logging.getLogger(__name__)

async def extract_details_from_text(user_text: str) -> dict:
    """Uses Gemini to extract structured data from a user's text message."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""You are an expert data extraction AI. Analyze the user's text to identify their intent and extract all relevant details for a quotation. Your response must be a raw JSON object.
The JSON object should have the following keys. If a key is not found, its value should be null or an empty array.
- 'doc_type': The type of quote. Must be one of 'sales', 'refurbish', or 'rental'.
- 'truck_number': The vehicle's registration number.
- 'company_name': The customer's name or company name.
- 'cust_contact': The customer's phone number.
- 'salesperson': The name of the salesperson.
- 'line_items': An array of objects for priced items. Each object must have "qty", "line_description", and "unit_price".
Rules:
1.  Infer the 'doc_type'. "Refurbish" or "repair" implies 'refurbish'. "Sale" or "sell" implies 'sales'. "Rent" or "sewa" implies 'rental'.
2.  For 'line_items', extract the description and the price. Assume quantity is 1 if not specified. For example, "Repair Pintu rm500" should become {{"qty": 1, "line_description": "Repair Pintu", "unit_price": 500}}.
3.  Your entire output must be ONLY the raw JSON. Do not include markdown or any other text.
User's Text:
"{user_text}"
"""
        response = await model.generate_content_async(prompt)
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        return safe_json_loads(json_text) # Use safe_json_loads
    except Exception as e:
        logger.error(f"Error in extract_details_from_text: {e}")
        return {}


async def extract_details_from_image(img: PIL.Image.Image) -> dict:
    """Uses Gemini to extract details from a draft quotation image or a vehicle grant."""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")
        prompt = f"""You are an expert data extraction AI. Your task is to analyze the provided image, which could be a vehicle grant (Geran) or a draft quotation, and extract information. Your response must be a raw JSON object.
Provide values for the following keys. If you cannot find a value for any key, you MUST return `null` for that key. Do not omit any keys.
- 'truck_number': The vehicle's registration number (e.g., "VFW 9558").
- 'body': The vehicle's body type (e.g., "Tipper", "Cargo").
- 'company_name': The customer's name or company name. (For Geran, this is the owner's name).
- 'company_address': The customer's full address.
- 'cust_contact': The customer's phone number.
- 'salesperson': The name of the salesperson.
- 'line_items': An array of objects for the main priced items. Each object must have "qty", "line_description", and "unit_price". If no items are found, return an empty array [].
- 'included_services': An array of strings listing services included (often without a price). If none, return an empty array [].
- 'payment_phases': An array of objects for the payment schedule. Each object must have "name" and "amount". If none, return an empty array [].
CRITICAL RULES:
1.  ALWAYS return a value (or `null`) for every key listed above.
2.  If the image is a vehicle grant (Geran), prioritize extracting 'truck_number', 'body', and the owner's name as 'company_name', and their address as 'company_address'. The other fields will likely be `null`.
3.  If the image is a business card or name card, prioritize extracting 'company_name', 'company_address', and 'cust_contact'.
4.  If the image is a draft quote, extract as much information as you can.
5.  If the image is unclear and you can only find one or two details (like just the truck number), that is acceptable. Return those details and `null` for the rest.
6.  Your entire output must be ONLY the raw JSON object, with no other text or markdown formatting.
"""
        response = await model.generate_content_async([prompt, img])
        json_text = response.text.strip().replace("```json", "").replace("```", "")
        return safe_json_loads(json_text) # Use safe_json_loads
    except Exception as e:
        logger.error(f"Error in extract_details_from_image: {e}")
        return {}
