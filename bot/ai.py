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


async def extract_details_from_image(image: PIL.Image.Image) -> dict:
    """
    Uses the Gemini API to extract details directly from an image.
    This leverages multimodal capabilities to understand layout and context
    from documents, truck photos, or business cards.

    Args:
        image: The image to process.

    Returns:
        A dictionary of extracted details.
    """
    model = genai.GenerativeModel("gemini-2.5-flash")
    prompt = """
    Analyze this image and extract specific details into a JSON object. 
    The image might be a document (invoice/quote), a photo of a vehicle (truck/lorry), or a business card.

    **Extraction Rules:**
    
    1. **Truck/Vehicle Photos:** 
       - **Company Name:** Prioritize the **visually largest** and **top-most** text block on the vehicle. This is usually the trade name (e.g., "AKI SERVICES").
       - **Ignore Regulatory Text:** Text containing "BARANG", "PEKERJA", "SDN SJA", "BDM", or "BTM" refers to permits/specs. Do not use these as the Company Name unless no other name exists.
       - **Number Plate:** Extract the vehicle registration number (e.g., 'BKG 9493').
       - **Address/Contact:** Extract any printed addresses or phone numbers.
       
    2. **Business Cards:**
       - Extract the Name, Company Name, Phone Number, and Address.
       
    3. **Documents:**
       - Extract details as usual, distinguishing between the recipient (Customer) and the sender.

    **Fields to Extract:**
    - doc_type (infer 'sales', 'rental', or 'refurbish' only if there is clear context. Otherwise null.)
    - truck_number (The vehicle number plate found in the image)
    - company_name (The **CUSTOMER'S** company name. On a truck, this is the name on the door. On a card, it's the company represented.)
    - company_address (The **CUSTOMER'S** address. It is usually located near the vehicle, card, or document.)
    - cust_contact (Phone number found on the vehicle, card, or document.)
    - body (The body type of the vehicle, if visually apparent or described)
    - salesperson (Name of person on a business card, or salesperson in a document)
    
    **For Rental Documents Only:**
    - rental_period_type (Infer 'monthly' or 'daily' based on context. Default to 'monthly' if unsure.)
    - contract_period (The duration of the contract, e.g., '1 Year', '6 Months', '2 Years')
    - rental_amount (The monthly or daily rental price)
    - security_deposit (The deposit amount)
    - road_tax_amount (Amount for road tax)
    - insurance_amount (Amount for insurance)
    - sticker_amount (Amount for stickers)
    - agreement_amount (Amount for agreement fees)
    - puspakom_amount (Amount for Puspakom inspection)

    - line_items (A list of general objects with 'line_description', 'qty', 'unit_price'. Use this for items NOT covered by the specific fields above.)

    Return the extracted details in JSON format.
    STRICTLY RETURN ONLY JSON. NO MARKDOWN. NO OTHER TEXT.
    """

    for attempt in range(3):
        try:
            response = await model.generate_content_async([prompt, image])
            text_response = response.text

            # Cleanup potential markdown
            cleaned_response = (
                text_response.strip().replace("```json", "").replace("```", "").strip()
            )

            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                # Fallback: Try to find the JSON object boundaries
                start = cleaned_response.find("{")
                end = cleaned_response.rfind("}") + 1
                if start != -1 and end != 0 and end > start:
                    json_str = cleaned_response[start:end]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.error(f"Fallback JSON parsing also failed: {e}")
                        raise
                else:
                    raise

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Attempt {attempt + 1} failed (Image Extraction): {e}")
            if attempt == 2:
                logger.error(f"Error calling Gemini API (Image) after 3 attempts: {e}")
                if "response" in locals():
                    logger.error(f"Final Raw API response: {response.text}")
                return {}
    return {}


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
    - doc_type (infer if it is 'sales', 'rental', or 'refurbish' based on keywords like 'rental', 'hire', 'sale', 'repair'. Default to null if unsure.)
    - truck_number (The vehicle number plate, e.g., 'BKG 9493')
    - company_name (The **CUSTOMER'S** company name (the recipient). Look for 'To:', 'Customer:', or simply the *other* company name on the document that is NOT the issuing company/sender.)
    - company_address (The **CUSTOMER'S** address. It is usually located near the customer's name. Do NOT use the sender's address.)
    - cust_contact (The customer's phone number)
    - body (The body type of the vehicle)
    - salesperson (The name of the salesperson)
    
    FOR RENTAL QUOTES, also extract these specific amounts if present:
    - rental_period_type (Infer 'monthly' or 'daily' based on context. Default to 'monthly' if unsure.)
    - contract_period (The duration of the contract, e.g., '1 Year', '6 Months', '2 Years')
    - rental_amount (The monthly or daily rental price)
    - security_deposit (The deposit amount)
    - road_tax_amount (Amount for road tax)
    - insurance_amount (Amount for insurance)
    - sticker_amount (Amount for stickers)
    - agreement_amount (Amount for agreement fees)
    - puspakom_amount (Amount for Puspakom inspection)

    - line_items (A list of general objects with 'line_description', 'qty', 'unit_price'. Use this for items NOT covered by the specific fields above.)

    Text:
    {text}

    Return the extracted details in JSON format.
    STRICTLY RETURN ONLY JSON. NO MARKDOWN. NO OTHER TEXT.
    """

    for attempt in range(3):
        try:
            response = await model.generate_content_async(prompt)
            text_response = response.text

            # Cleanup potential markdown
            cleaned_response = (
                text_response.strip().replace("```json", "").replace("```", "").strip()
            )

            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                # Fallback: Try to find the JSON object boundaries
                start = cleaned_response.find("{")
                end = cleaned_response.rfind("}") + 1
                if start != -1 and end != 0 and end > start:
                    json_str = cleaned_response[start:end]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.error(f"Fallback JSON parsing also failed: {e}")
                        raise
                else:
                    raise

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt == 2:
                logger.error(
                    f"Error calling Gemini API or parsing JSON after 3 attempts: {e}"
                )
                if "response" in locals():
                    logger.error(f"Final Raw API response: {response.text}")
                return {}
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
        response = await model.generate_content_async(
            ["Transcribe all text from this image.", image]
        )
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
    Extract the line items from the text below. Each item should have a 'line_description', 'qty', and 'unit_price'.
    If quantity is not mentioned, assume it is 1.
    If a line does not contain a price, it is not a line item and should be ignored.
    The output MUST be a valid JSON list of objects. Each object in the list MUST contain 'line_description', 'qty', and 'unit_price' keys.

    Text:
    {text}

    Return a valid JSON list of objects. For example:
    [
        {{"line_description": "New Lorry", "qty": 1, "unit_price": 150000}},
        {{"line_description": "Service B", "qty": 2, "unit_price": 250}}
    ]
    
    Return the extracted details in a STRICT, VALID JSON format. 
    Do not include any Markdown formatting (no ```json or ```).
    STRICTLY RETURN ONLY JSON. NO MARKDOWN. NO OTHER TEXT.
    """

    for attempt in range(3):
        try:
            response = await model.generate_content_async(prompt)
            text_response = response.text

            # Cleanup potential markdown
            cleaned_response = (
                text_response.strip().replace("```json", "").replace("```", "").strip()
            )

            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                # Fallback: Try to find the JSON list boundaries
                start = cleaned_response.find("[")
                end = cleaned_response.rfind("]") + 1
                if start != -1 and end != 0 and end > start:
                    json_str = cleaned_response[start:end]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError as e:
                        logger.error(f"Fallback line items parsing also failed: {e}")
                        raise
                else:
                    raise

        except (json.JSONDecodeError, Exception) as e:
            logger.warning(f"Attempt {attempt + 1} failed in extract_line_items: {e}")
            if attempt == 2:
                logger.error(
                    f"Error in extract_line_items_from_text after 3 attempts: {e}"
                )
                if "response" in locals():
                    logger.error(f"Raw API response: {response.text}")
                return []
    return []
