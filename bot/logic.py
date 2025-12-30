import logging
import json
import os
import httpx  # Changed from requests
from datetime import datetime, date
import telegram
from typing import Union

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

# Internal imports
from .constants import *
from .helpers import (
    get_display_value,
    search_customer_by_name,
    validate_date,
    get_gl_code_for_service,
)
from .templates import build_confirmation_text, missing_field_prompt
from .keyboards import (
    build_doc_type_keyboard,
    build_review_keyboard,
    build_confirm_generate_keyboard,
    build_rental_period_keyboard,
    build_equipment_keyboard,
    build_post_generation_keyboard,
    build_main_services_keyboard,
    build_additional_services_keyboard,
    build_line_item_review_keyboard,
    build_skip_keyboard,
    build_service_review_keyboard,
    build_payment_phase_review_keyboard,
)

logger = logging.getLogger(__name__)


API_URL_LOCAL = os.getenv("API_URL", "http://localhost:8000/generate_quotation_pdf/")


async def ask_for_doc_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks the user to select the document type."""
    reply_markup = build_doc_type_keyboard()
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    await message.reply_text(
        "What type of quote would you like to create?", reply_markup=reply_markup
    )


async def show_main_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the main services menu for selection."""
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    context.user_data["state"] = SELECTING_MAIN_SERVICE
    reply_markup = build_main_services_keyboard(context.user_data)
    await message.reply_text(
        "Please select the services you want to include:", reply_markup=reply_markup
    )


async def show_additional_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the additional services menu for selection."""
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    context.user_data["state"] = SELECTING_ADDITIONAL_SERVICES
    reply_markup = build_additional_services_keyboard(context.user_data)
    await message.reply_text(
        "Please select any additional services:", reply_markup=reply_markup
    )


async def check_customer_in_database(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """
    Step 6: Use the new server-side search to find potential customer matches.
    """
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    user_provided_name = context.user_data.get("company_name")

    if not user_provided_name:
        context.user_data["customer_checked"] = True
        context.user_data["is_new_customer"] = True
        await check_and_transition(update, context)
        return

    found_customers = await search_customer_by_name(
        user_provided_name
    )  # Await the async call

    if found_customers and "error" not in found_customers:
        logger.info(
            f"Found {len(found_customers)} potential match(es) for '{user_provided_name}'."
        )

        if len(found_customers) == 1:
            matched_name = list(found_customers.keys())[0]
            context.user_data["matched_customer_name"] = matched_name
            keyboard = [
                [
                    InlineKeyboardButton(
                        f"Yes, use data for '{matched_name}'",
                        callback_data="use_existing_customer",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "No, this is a new customer", callback_data="use_extracted_data"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"I found a possible match: '{matched_name}'. Is this the correct customer?",
                reply_markup=reply_markup,
            )
        else:
            keyboard = [
                [
                    InlineKeyboardButton(
                        name, callback_data=f"select_matched_customer_{name}"
                    )
                ]
                for name in found_customers.keys()
            ]
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "None of these are correct", callback_data="use_extracted_data"
                    )
                ]
            )
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=message.chat_id,
                text="I found several possible matches. Please select the correct one:",
                reply_markup=reply_markup,
            )

    else:
        logger.info(
            f"New customer '{user_provided_name}' - no match found in database."
        )
        context.user_data["customer_checked"] = True
        context.user_data["is_new_customer"] = True
        await check_and_transition(update, context)


async def start_rental_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the detailed question flow for a rental quote."""
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    context.user_data["state"] = WAITING_FOR_RENTAL_PERIOD
    reply_markup = build_rental_period_keyboard()
    await context.bot.send_message(
        chat_id=message.chat_id,
        text="Is this a daily or monthly rental?",
        reply_markup=reply_markup,
    )


async def ask_for_lorry_sale_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks user to select the lorry sale type when price is not known."""
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "Lorry Harga OTR", callback_data="lorry_sale_type_Lorry Price OTR"
            )
        ],
        [
            InlineKeyboardButton(
                "Lorry harga Shj", callback_data="lorry_sale_type_Lorry harga Shj"
            )
        ],
        [InlineKeyboardButton("Offroad", callback_data="lorry_sale_type_Offroad")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=message.chat_id,
        text="What type of lorry sale is this?",
        reply_markup=reply_markup,
    )


async def ask_for_issuing_company(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dynamically creates company selection buttons from the config file."""
    from company_config import COMPANY_ADDRESSES

    keyboard = [
        [InlineKeyboardButton(name.title(), callback_data=f"company_{name}")]
        for name in COMPANY_ADDRESSES.keys()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message = update.callback_query.message if update.callback_query else update.message
    sent_message = await message.reply_text(
        "Please choose the issuing company:", reply_markup=reply_markup
    )
    # Store the message ID so we can edit it later
    context.user_data["company_selection_message_id"] = sent_message.message_id


async def ask_for_price_clarification(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Asks the user to clarify if a price is total or per piece."""
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )

    items_to_clarify = context.user_data.get("items_to_clarify", [])

    if not items_to_clarify:
        # All items clarified, proceed to the next step
        context.user_data["state"] = WAITING_FOR_COMPANY
        await check_and_transition(update, context)
        return

    # Pop the first item to clarify
    item_index, item = items_to_clarify.pop(0)

    desc = item["line_description"]
    qty = item["qty"]
    price = item["unit_price"]

    question = (
        f"For the item:\n"
        f"'{desc}' (x{qty})\n"
        f"You entered a price of RM {price:,.2f}. Is this the TOTAL price for all {qty} items, or is it the price PER PIECE?"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "Total Price", callback_data=f"clarify_total_{item_index}"
            ),
            InlineKeyboardButton(
                "Price Per Piece", callback_data=f"clarify_perpiece_{item_index}"
            ),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=message.chat_id, text=question, reply_markup=reply_markup
    )


def rebuild_rental_fee_items(context: ContextTypes.DEFAULT_TYPE):
    """
    Silently rebuilds the service_line_items list with the current rental fee values.
    Does NOT send messages, change state, or reset equipment.
    Handles 'excluded' items for monthly rentals by placing them in a separate list.
    """
    is_monthly = context.user_data.get("rental_period_type") == "monthly"

    filtered_service_line_items = []
    excluded_line_items = []

    fees_config = [
        ("road_tax", "Road Tax", "930-000"),
        ("insurance", "Insurance", "931-000"),
        ("sticker", "Sticker", "501-000"),
        ("agreement", "Agreement Fee", "501-000"),
        ("puspakom", "PUSPAKOM Fee", "930-000"),
    ]

    # Hardcode Maintenance for monthly rentals
    if is_monthly:
        excluded_line_items.append(
            {
                "qty": 1,
                "line_description": "Maintenance (Every 3month/5000km, which ever comes first)",
                "unit_price": 0.0,
                "gl_code": "501-000",
            }
        )

    for fee_key, fee_name, gl_code in fees_config:
        amount_key = f"{fee_key}_amount"
        excluded_key = f"{fee_key}_is_excluded"

        if context.user_data.get(amount_key) is not None:
            try:
                amount = float(context.user_data[amount_key])
            except (ValueError, TypeError):
                logger.warning(
                    f"Could not convert {amount_key} to float. Value was: {context.user_data[amount_key]}"
                )
                continue  # Skip this fee if amount is invalid

            is_excluded = context.user_data.get(excluded_key, False)

            description = fee_name  # Default

            if is_monthly:
                if fee_key in ["agreement", "sticker"]:
                    description = fee_name  # Just "Agreement Fee" or "Sticker"
                else:
                    period_text = "(Every 6 Month)"
                    included_text = "(Included every 6month)"

                    if amount == 0 and not is_excluded:
                        description = f"{fee_name} {included_text}"
                    else:
                        description = f"{fee_name} {period_text}"
            else:
                if amount == 0:
                    description = f"{fee_name} (Included)"
                else:
                    description = f"{fee_name}"

            item = {
                "qty": 1,
                "line_description": description,
                "unit_price": amount,
                "gl_code": gl_code,
            }

            if is_monthly and is_excluded:
                excluded_line_items.append(item)
            else:
                filtered_service_line_items.append(item)

    context.user_data["service_line_items"] = filtered_service_line_items
    context.user_data["excluded_line_items"] = excluded_line_items

    logger.info("--- Rebuild Rental Fees ---")
    logger.info(
        f"Service Line Items: {json.dumps(filtered_service_line_items, indent=2)}"
    )
    logger.info(f"Excluded Line Items: {json.dumps(excluded_line_items, indent=2)}")
    logger.info("---------------------------")


async def ask_for_next_rental_fee(
    update: Update, context: ContextTypes.DEFAULT_TYPE, fee_to_ask: str = None
):
    """
    Asks the user about the next rental fee in the sequence.
    Manages the sub-flow for collecting rental fees like road tax, insurance, etc.
    If 'fee_to_ask' is provided, it will only ask for that specific fee.
    """
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )

    if fee_to_ask:
        fees_to_ask = [fee_to_ask]
    else:
        # The list of fees to process
        if "fees_to_ask" not in context.user_data:
            context.user_data["fees_to_ask"] = [
                "road_tax",
                "insurance",
                "puspakom",
                "sticker",
                "agreement",
            ]
        fees_to_ask = context.user_data["fees_to_ask"]

    if not fees_to_ask:
        # Use the shared logic to rebuild items
        rebuild_rental_fee_items(context)

        context.user_data["rental_fees_collected"] = True
        # Pre-select default equipment
        context.user_data["selected_equipment"] = DEFAULT_RENTAL_EQUIPMENT.copy()
        await show_equipment_checklist(
            update, context
        )  # This is now imported from .logic
        return

    next_fee = fees_to_ask[0]  # Peek at the next fee
    fee_name = next_fee.replace("_", " ").title()

    is_monthly = context.user_data.get("rental_period_type") == "monthly"

    # Default button texts
    btn_price_text = "Enter Price"
    btn_included_text = "Included in Package"
    btn_excluded_text = "Excluded"

    if is_monthly:
        if next_fee in ["road_tax", "insurance", "puspakom"]:
            btn_price_text = "Every 6 Month"
            btn_included_text = "Included every 6month"
            btn_excluded_text = "Not Included"

    # Custom button texts for specific fees
    if next_fee == "sticker":
        btn_excluded_text = "Not Included"
    elif next_fee == "agreement":
        btn_excluded_text = "Excluded"

    keyboard = [
        [
            InlineKeyboardButton(
                btn_price_text, callback_data=f"rental_price_{next_fee}"
            )
        ],
        [
            InlineKeyboardButton(
                btn_included_text, callback_data=f"rental_included_{next_fee}"
            )
        ],
        [
            InlineKeyboardButton(
                btn_excluded_text, callback_data=f"rental_skip_{next_fee}"
            )
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=message.chat_id,
        text=f"What about {fee_name}?",
        reply_markup=reply_markup,
    )


async def send_confirmation_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE, is_review=False
):
    """
    Sends or edits a summary of the collected data for user confirmation/review,
    ensuring a single, persistent confirmation message is used.
    """
    # Get the chat_id more reliably
    if update.message:
        chat_id = update.message.chat_id
    elif update.callback_query:
        chat_id = update.callback_query.message.chat_id
    else:
        logger.error("Could not determine chat_id in send_confirmation_message")
        return

    confirmation_text = build_confirmation_text(context.user_data, is_review)

    if is_review:
        reply_markup = build_review_keyboard()
        context.user_data["state"] = REVIEWING_EXTRACTED_DATA
    else:
        reply_markup = build_confirm_generate_keyboard(context.user_data)
        context.user_data["state"] = CONFIRMING_DETAILS

    confirmation_message_id = context.user_data.get("confirmation_message_id")

    if confirmation_message_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=confirmation_message_id,
                text=confirmation_text,
                reply_markup=reply_markup,
            )
            logger.info(
                f"Successfully edited confirmation message {confirmation_message_id}"
            )
            return
        except telegram.error.BadRequest as e:
            logger.warning(
                f"Failed to edit confirmation message (ID: {confirmation_message_id}): {e}. Sending a new one."
            )
            context.user_data.pop("confirmation_message_id", None)
        except telegram.error.TimedOut as e:
            logger.warning(f"Timeout editing message: {e}. Sending a new one.")
            context.user_data.pop("confirmation_message_id", None)

    # Send a new message
    logger.info("Sending new confirmation message")
    sent_message = await context.bot.send_message(
        chat_id=chat_id, text=confirmation_text, reply_markup=reply_markup
    )
    context.user_data["confirmation_message_id"] = sent_message.message_id
    logger.info(f"New confirmation message sent with ID: {sent_message.message_id}")


def _clean_amount_string(amount_str: Union[str, float]) -> float:
    """Removes commas from amount strings and converts to float."""
    if isinstance(amount_str, float):
        return amount_str
    try:
        return float(str(amount_str).replace(",", ""))
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not convert '{amount_str}' to float: {e}")
        return 0.0


async def dispatch_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatches the final payload to the API."""
    chat_id = update.effective_chat.id
    data = context.user_data
    doc_type = data.get("doc_type", "none")

    # Support both new and old flag names for compatibility
    is_proforma = data.get("is_proforma", False) or data.get(
        "is_proforma_display", False
    )
    logger.info(f"Dispatching request. is_proforma resolved to: {is_proforma}")

    if is_proforma:
        description = "Proforma Invoice"
    else:
        description = f"{doc_type.capitalize()} Quotation for truck {data.get('truck_number', '')}"

    # Log the full user_data context for debugging
    logger.info(
        "--- DISPATCHING REQUEST: FULL USER_DATA ---\n%s",
        json.dumps(data, indent=2, default=str),
    )

    # --- New: Dynamic Prefix Generation ---
    issuing_company_name = data.get("issuing_company", "Unique Enterprise").upper()

    company_prefixes = {
        "UNIQUE ENTERPRISE": "UE",
        "CARTRUCKVAN SDN. BHD.": "CTV",
    }
    company_prefix = company_prefixes.get(issuing_company_name, "QT")  # Default to QT

    doc_type_prefixes = {
        "sales": "SQ",
        "refurbish": "RQ",
        "rental": "RN",
    }
    doc_type_prefix = doc_type_prefixes.get(doc_type, "QT")  # Default to QT

    truck_num_part = (data.get("truck_number") or "MISC").replace("/", "-")
    date_part = datetime.now().strftime("%d%m%y")

    # Construct the doc_no
    doc_no = f"{company_prefix}{doc_type_prefix}-{truck_num_part}-{date_part}"

    # Clean up customer address to remove extra blank lines
    company_address = data.get("company_address", "")
    cleaned_address = "\n".join(
        [line.strip() for line in company_address.split("\n") if line.strip()]
    )

    payload = {
        "type": doc_type,
        "cust_code": "300-C0002",
        "cust_name": data.get("company_name", "CASH SALE"),
        "company_address": cleaned_address,
        "cust_contact": data.get("cust_contact", ""),
        "truck_number": data.get("truck_number", ""),
        "issuing_company": issuing_company_name,
        "doc_no": doc_no,
        "description": description,
        "salesperson": data.get("salesperson"),
        "payment_phases": data.get("payment_phases", []),
        "is_proforma": is_proforma,
    }

    # Normalize and filter line items
    raw_line_items = data.get("line_items", [])
    line_items = []
    for item in raw_line_items:
        if isinstance(item, dict):
            # Handle both 'description' and 'line_description'
            desc = item.get("line_description") or item.get("description")
            if desc:
                line_items.append(
                    {
                        "qty": item.get("qty", 1),
                        "line_description": desc,
                        "unit_price": _clean_amount_string(item.get("unit_price", 0)),
                        "gl_code": item.get("gl_code")
                        or get_gl_code_for_service(desc)
                        or "501-000",
                    }
                )

    raw_service_items = data.get("service_line_items", [])
    service_line_items = []
    for item in raw_service_items:
        if isinstance(item, dict):
            desc = item.get("line_description") or item.get("description")
            if desc:
                service_line_items.append(
                    {
                        "qty": item.get("qty", 1),
                        "line_description": desc,
                        "unit_price": _clean_amount_string(item.get("unit_price", 0)),
                        "gl_code": item.get("gl_code")
                        or get_gl_code_for_service(desc)
                        or "501-000",
                    }
                )

    raw_excluded_items = data.get("excluded_line_items", [])
    excluded_line_items = []
    for item in raw_excluded_items:
        if isinstance(item, dict):
            desc = item.get("line_description") or item.get("description")
            if desc:
                excluded_line_items.append(
                    {
                        "qty": item.get("qty", 1),
                        "line_description": desc,
                        "unit_price": _clean_amount_string(item.get("unit_price", 0)),
                        "gl_code": item.get("gl_code")
                        or get_gl_code_for_service(desc)
                        or "501-000",
                    }
                )

    # Update the payload with normalized lists
    payload["line_items"] = line_items
    payload["service_line_items"] = service_line_items
    payload["excluded_line_items"] = excluded_line_items

    # Total amount calculation
    total_amount = sum(item["unit_price"] * item["qty"] for item in line_items)
    total_amount += sum(item["unit_price"] * item["qty"] for item in service_line_items)

    if doc_type.startswith("rental"):
        if "rental_amount" in data:
            rental_desc = "Monthly Rental"
            if data.get("rental_period_type") == "daily":
                days = data.get("rental_days", "N/A")
                start_date = data.get("rental_start_date", "N/A")
                end_date = data.get("rental_end_date", "N/A")
                rental_desc = f"{start_date} to {end_date} ({days} Days)"

            payload["main_rental_item"] = {
                "qty": 1,
                "line_description": rental_desc,
                "unit_price": _clean_amount_string(data.get("rental_amount", 0)),
                "gl_code": "535-000",
            }
            payload["security_deposit"] = _clean_amount_string(
                data.get("security_deposit", 0)
            )

            total_amount += _clean_amount_string(data.get("rental_amount", 0))
            total_amount += _clean_amount_string(data.get("security_deposit", 0))

        start_date_val, end_date_val = data.get("rental_start_date"), data.get(
            "rental_end_date"
        )
        start_date_str = (
            start_date_val.strftime("%Y-%m-%d")
            if isinstance(start_date_val, date)
            else start_date_val
        )
        end_date_str = (
            end_date_val.strftime("%Y-%m-%d")
            if isinstance(end_date_val, date)
            else end_date_val
        )

        payload.update(
            {
                "rental_period_type": data.get("rental_period_type", "monthly"),
                "contract_period": data.get("contract_period"),
                "rental_start_date": start_date_str,
                "rental_end_date": end_date_str,
                "rental_days": data.get("rental_days", "N/A"),
                "selected_equipment": data.get("selected_equipment", []),
            }
        )

    payload["total_amount"] = total_amount
    payload["body"] = data.get("body", "")

    logger.info(
        "--- FINAL DISPATCHING PAYLOAD ---\n%s",
        json.dumps(payload, indent=2, default=str),
    )
    context.bot_data["last_payload"] = payload

    await context.bot.send_message(
        chat_id=chat_id, text=f"Generating PDF for {doc_type}..."
    )
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(API_URL_LOCAL, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("success"):
            file_path = result.get("file_path")
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Generated PDF not found at {file_path}")

            await context.bot.send_message(
                chat_id=chat_id,
                text="PDF generated successfully! Sending it to you now...",
            )
            with open(file_path, "rb") as pdf_file:
                await context.bot.send_document(chat_id=chat_id, document=pdf_file)

            context.user_data["state"] = POST_GENERATION
            reply_markup = build_post_generation_keyboard()
            await context.bot.send_message(
                chat_id=chat_id,
                text="✅ Done! You can now choose to 'edit' these details, or say 'new' to start over.",
                reply_markup=reply_markup,
            )
        else:
            error_msg = result.get("detail", "Unknown error")
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ API Error: {error_msg}\n\nYour data is saved. Try /start to retry.",
            )
    except Exception as e:
        logger.exception("Unexpected error in dispatch_request")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Unexpected error: {str(e)}\n\nYour data is saved. Try /start to retry.",
        )


async def check_and_transition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    The central state machine that decides what information to ask for next.
    """
    # --- Start Diagnosis Logging ---
    logger.info("--- CHECK_AND_TRANSITION CALLED ---")
    try:
        user_data_json = json.dumps(context.user_data, indent=2, default=str)
        logger.info("USER_DATA at start of check_and_transition:\n%s", user_data_json)
    except Exception as e:
        logger.error(f"Could not serialize user_data for logging: {e}")
    # --- End Diagnosis Logging ---

    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    data = context.user_data
    doc_type = data.get("doc_type")

    # Step 1: Ensure we have a document type
    if not doc_type:
        context.user_data["state"] = AWAITING_DOC_TYPE
        await ask_for_doc_type(update, context)
        return

    # Step 6: Check if we've done the customer database check yet (Feature Disabled)
    data["is_new_customer"] = True
    data["customer_checked"] = True

    # --- New: Contextual Company Name Handling (after doc_type is known) ---
    if data.get("is_company_name_from_image_extracted") and data.get(
        "extracted_image_company_name"
    ):
        extracted_name = data["extracted_image_company_name"]

        if doc_type.startswith("refurbish"):
            # Also applies to refurbish_proforma
            # For refurbish, automatically use the name from the image
            data["company_name"] = extracted_name
            if "extracted_image_company_address" in data:
                data["company_address"] = data["extracted_image_company_address"]

            # Clean up temporary flags
            data.pop("is_company_name_from_image_extracted", None)
            data.pop("extracted_image_company_name", None)
            data.pop(
                "extracted_image_company_address", None
            )  # If address was extracted from image
            logger.info(
                f"Refurbish quote: Auto-using company name from image: {extracted_name}"
            )
            # Recursively call check_and_transition to continue the flow
            await check_and_transition(update, context)
            return

        elif doc_type.startswith("sales") or doc_type.startswith(
            "rental"
        ):  # Applies to sales/rental and their proformas
            # For sales/rental, ask for confirmation
            context.user_data["state"] = AWAITING_COMPANY_NAME_CONFIRMATION
            keyboard = [
                [
                    InlineKeyboardButton(
                        f"Yes, use '{extracted_name}'",
                        callback_data="confirm_company_name_yes",
                    )
                ],
                [
                    InlineKeyboardButton(
                        "No, enter new name", callback_data="confirm_company_name_no"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"I extracted a company name '{extracted_name}' from the image. Is this the customer's name for your {doc_type} quote?",
                reply_markup=reply_markup,
            )
            return

    # --- End: Contextual Company Name Handling ---

    # Step 7: Now check for ALL required fields
    required_fields = {
        "company_name": "customer company name",
        "company_address": "customer company address",
        "cust_contact": "customer's phone number",
        "salesperson": "salesperson's name",
        "truck_number": "truck number (e.g., 'VAN 5222')",
    }
    if doc_type.startswith("sales") or doc_type.startswith(
        "refurbish"
    ):  # Also applies to sales_proforma/refurbish_proforma
        required_fields.update({"body": "body type"})

    # Check each required field
    for field, prompt in required_fields.items():
        field_value = data.get(field)
        # A field is considered missing if it's None or an empty string.
        # "0" or "N/A" are now considered provided (though hidden on PDF).
        if not field_value and str(field_value).strip().upper() not in ["0", "N/A"]:
            context.user_data["state"] = AWAITING_INFO
            context.user_data["waiting_for_field"] = field
            reply_markup = build_skip_keyboard()
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=missing_field_prompt(prompt),
                reply_markup=reply_markup,
            )
            return

    # --- New Position for Issuing Company Check ---
    # Ask for issuing company right after basic details, before doc-specific flows
    issuing_company = data.get("issuing_company", "")
    logger.info(
        f"DEBUG: Checking issuing_company value: '{issuing_company}' (type: {type(issuing_company)})"
    )

    if (
        not issuing_company
        or str(issuing_company).strip() == ""
        or str(issuing_company).strip().upper() == "N/A"
    ):
        logger.info(
            "DEBUG: Issuing company is missing/N/A. Transitioning to WAITING_FOR_COMPANY."
        )
        context.user_data["state"] = WAITING_FOR_COMPANY
        await ask_for_issuing_company(update, context)
        return
    else:
        logger.info("DEBUG: Issuing company considered valid. Skipping selection.")

    # All basic info collected! Now proceed to doc-specific flows
    if doc_type.startswith("rental"):  # Also applies to rental_proforma
        rental_period_type = data.get("rental_period_type")
        if rental_period_type == "daily":
            if not all(
                key in data
                for key in [
                    "rental_start_date",
                    "rental_end_date",
                    "rental_amount",
                    "security_deposit",
                ]
            ):
                await start_rental_flow(update, context)
                return
        elif rental_period_type == "monthly":
            if not all(
                key in data
                for key in ["contract_period", "rental_amount", "security_deposit"]
            ):
                await start_rental_flow(update, context)
                return
        else:  # If rental_period_type is not set at all
            await start_rental_flow(update, context)
            return

        # If we get here, all details for either daily or monthly are collected
        data["rental_details_collected"] = True

        # Now, check for fee/equipment steps if they haven't been done
        if not data.get("rental_fees_collected") or not data.get(
            "rental_equipment_collected"
        ):
            # This will trigger the ask_for_next_rental_fee -> show_equipment_checklist chain
            await ask_for_next_rental_fee(update, context)
            return

    elif doc_type.startswith("sales"):  # Also applies to sales_proforma
        if not data.get("lorry_sale_item_created"):
            if data.get("line_items"):
                price = data["line_items"][0].get("unit_price", "N/A")
                message_text = f"I see the lorry price is RM {price}. Please clarify the description:"
                context.user_data["state"] = SELECTING_LORRY_SALE_TYPE
                keyboard = [
                    [
                        InlineKeyboardButton(
                            "Lorry Price OTR",
                            callback_data="clarify_sale_type_Lorry Price OTR",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Lorry Harga SHJ",
                            callback_data="clarify_sale_type_Lorry Harga SHJ",
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "Offroad", callback_data="clarify_sale_type_Offroad"
                        )
                    ],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await message.reply_text(message_text, reply_markup=reply_markup)
            else:
                context.user_data["state"] = SELECTING_LORRY_SALE_TYPE
                await ask_for_lorry_sale_type(update, context)
            return

        if not data.get("main_services_done"):
            context.user_data["state"] = SELECTING_MAIN_SERVICE
            await show_main_services(update, context)
            return

        if not data.get("additional_services_done"):
            context.user_data["state"] = SELECTING_ADDITIONAL_SERVICES
            await show_additional_services(update, context)
            return

        if not data.get("payment_phases_complete"):
            context.user_data["state"] = ASK_FOR_PAYMENT_PHASES
            keyboard = [
                [InlineKeyboardButton("Yes", callback_data="payment_phase_yes")],
                [InlineKeyboardButton("No", callback_data="payment_phase_no")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=message.chat_id,
                text="Do you want to add a phased payment schedule?",
                reply_markup=reply_markup,
            )
            return

    elif doc_type.startswith("refurbish"):  # Also applies to refurbish_proforma
        if not data.get("line_items"):
            context.user_data["state"] = AWAITING_INFO
            context.user_data["waiting_for_field"] = "line_items"
            await context.bot.send_message(
                chat_id=message.chat_id,
                text="I need the line items for the refurbish quote (e.g., '1 unit rm10000' or 'description - RM price'). Please provide them.",
            )
            return

    # Everything collected! Show final confirmation
    await send_confirmation_message(update, context, is_review=False)


async def show_equipment_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks the user to select equipment for the rental."""
    context.user_data["state"] = SELECTING_EQUIPMENT
    reply_markup = build_equipment_keyboard(
        context.user_data.get("selected_equipment", [])
    )
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )

    # If called from a callback, edit the message. Otherwise, send a new one.
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text="Please select the equipment provided:", reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text="Please select the equipment provided:",
            reply_markup=reply_markup,
        )


async def ask_for_line_item_review(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Asks the user to review the extracted line items."""
    line_items = context.user_data.get("line_items", [])
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )

    if not line_items:
        await message.reply_text("No line items extracted. Please provide them.")
        context.user_data["state"] = AWAITING_INFO
        context.user_data["waiting_for_field"] = "line_items"
        return

    context.user_data["state"] = REVIEWING_LINE_ITEMS
    reply_markup = build_line_item_review_keyboard(line_items)
    await message.reply_text(
        "Here are the line items I extracted. Please review them.",
        reply_markup=reply_markup,
    )


async def ask_for_service_review(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Asks the user to review the selected services."""
    from .keyboards import build_service_review_keyboard

    service_line_items = context.user_data.get("service_line_items", [])
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )

    if not service_line_items:
        await message.reply_text("No services selected.")
        # Transition back to main selection?
        context.user_data["state"] = SELECTING_MAIN_SERVICE
        await show_main_services(update, context)
        return

    # No specific state needed if we handle callbacks generically,
    # but setting one helps tracking.
    # context.user_data["state"] = REVIEWING_SERVICES # Define if needed
    reply_markup = build_service_review_keyboard(service_line_items)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Here are the services you selected. You can edit their prices or remove them.",
            reply_markup=reply_markup,
        )
    else:
        await message.reply_text(
            "Here are the services you selected. You can edit their prices or remove them.",
            reply_markup=reply_markup,
        )


def recalculate_final_payment(user_data: dict) -> None:
    """


    Recalculates the amount for the 'Final Payment' phase and ensures


    correct ordering (1st, 2nd... Final).


    """

    from .helpers import to_ordinal

    line_items = user_data.get("line_items", [])

    service_items = user_data.get("service_line_items", [])

    total_amount = sum(
        item.get("unit_price", 0) * item.get("qty", 1) for item in line_items
    )

    total_amount += sum(
        item.get("unit_price", 0) * item.get("qty", 1) for item in service_items
    )

    if user_data.get("doc_type") == "rental":

        total_amount += user_data.get("rental_amount", 0)

        total_amount += user_data.get("security_deposit", 0)

    phases = user_data.get("payment_phases", [])

    if not phases:

        return

    # 1. Filter out Final Payment and collect others

    other_phases = [p for p in phases if p.get("name") != "Final Payment"]

    final_phase = next((p for p in phases if p.get("name") == "Final Payment"), None)

    # 2. Re-name other phases based on their current order

    new_phases = []

    other_total = 0

    for i, phase in enumerate(other_phases):

        phase["name"] = f"{to_ordinal(i+1)} Payment"

        new_phases.append(phase)

        other_total += phase.get("amount", 0)

    # 3. Handle Final Payment

    balance = total_amount - other_total

    if final_phase:

        final_phase["amount"] = balance

    else:

        final_phase = {"name": "Final Payment", "amount": balance, "remarks": ""}

    new_phases.append(final_phase)

    user_data["payment_phases"] = new_phases

    # Update counter for next 'add another' action

    user_data["payment_phase_counter"] = len(other_phases) + 1


async def ask_for_payment_phase_review(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Asks the user to review the payment phases."""
    from .keyboards import build_payment_phase_review_keyboard

    phases = context.user_data.get("payment_phases", [])
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )

    if not phases:
        await message.reply_text("No payment phases defined.")
        return

    context.user_data["state"] = SELECTING_PAYMENT_PHASE_TO_EDIT
    reply_markup = build_payment_phase_review_keyboard(context.user_data)

    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Here are the payment phases. You can edit or remove them.",
            reply_markup=reply_markup,
        )
    else:
        await message.reply_text(
            "Here are the payment phases. You can edit or remove them.",
            reply_markup=reply_markup,
        )
