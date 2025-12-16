import logging
import json
import os
import requests
from datetime import datetime, date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update # Added Update
from telegram.ext import ContextTypes

# Internal imports
from .constants import *
from .helpers import get_display_value, search_customer_by_name, validate_date # Added validate_date
from .templates import build_confirmation_text, missing_field_prompt
from .keyboards import (
    build_doc_type_keyboard, build_review_keyboard, 
    build_confirm_generate_keyboard, build_rental_period_keyboard,
    build_equipment_keyboard # Added build_equipment_keyboard
)

logger = logging.getLogger(__name__)

API_URL_LOCAL = "http://127.0.0.1:8000/generate_quotation_pdf/"

async def ask_for_doc_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks the user to select the document type."""
    reply_markup = build_doc_type_keyboard()
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    await message.reply_text(
        "What type of quote would you like to create?", reply_markup=reply_markup
    )

async def show_services_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the service checklist, retrieving the current path from user_data."""
    from services_config import SALES_SERVICES
    from .keyboards import build_services_keyboard

    query = update.callback_query
    message = update.message or (query.message if query else None)
    
    category_path = context.user_data.get('service_menu_path', [])
    selected_services = context.user_data.get("selected_services", [])
    
    reply_markup = build_services_keyboard(SALES_SERVICES, category_path, selected_services)
    message_text = "Please select any additional services to be included."

    if query:
        # To avoid a crash, only edit if the markup has actually changed.
        if query.message.reply_markup != reply_markup:
            try:
                await query.edit_message_text(text=message_text, reply_markup=reply_markup)
            except telegram.error.BadRequest as e:
                # Log errors other than "message not modified"
                if "Message is not modified" not in str(e):
                    logger.error(f"Error updating service checklist: {e}")
        else:
            # Answer the callback to provide feedback to the user (e.g., stops the loading icon)
            await query.answer()
    else:
        await message.reply_text(text=message_text, reply_markup=reply_markup)

async def check_customer_in_database(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Step 6: Use the new server-side search to find potential customer matches.
    """
    message = update.message or (update.callback_query.message if update.callback_query else None)
    user_provided_name = context.user_data.get('company_name')
    
    if not user_provided_name:
        context.user_data['customer_checked'] = True
        context.user_data['is_new_customer'] = True
        await check_and_transition(update, context)
        return
    
    found_customers = search_customer_by_name(user_provided_name)
    
    if found_customers and "error" not in found_customers:
        logger.info(f"Found {len(found_customers)} potential match(es) for '{user_provided_name}'.")
        
        if len(found_customers) == 1:
            matched_name = list(found_customers.keys())[0]
            context.user_data['matched_customer_name'] = matched_name
            keyboard = [
                [InlineKeyboardButton(f"Yes, use data for '{matched_name}'", callback_data='use_existing_customer')],
                [InlineKeyboardButton("No, this is a new customer", callback_data='use_extracted_data')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=message.chat_id, 
                text=f"I found a possible match: '{matched_name}'. Is this the correct customer?", 
                reply_markup=reply_markup
            )
        else:
            keyboard = [
                [InlineKeyboardButton(name, callback_data=f"select_matched_customer_{name}")] for name in found_customers.keys()
            ]
            keyboard.append([InlineKeyboardButton("None of these are correct", callback_data='use_extracted_data')])
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=message.chat_id, 
                text="I found several possible matches. Please select the correct one:", 
                reply_markup=reply_markup
            )

    else:
        logger.info(f"New customer '{user_provided_name}' - no match found in database.")
        context.user_data['customer_checked'] = True
        context.user_data['is_new_customer'] = True
        await check_and_transition(update, context)

async def start_rental_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts the detailed question flow for a rental quote."""
    message = update.message or (update.callback_query.message if update.callback_query else None)
    context.user_data["state"] = WAITING_FOR_RENTAL_PERIOD
    reply_markup = build_rental_period_keyboard()
    await context.bot.send_message(chat_id=message.chat_id, text="Is this a daily or monthly rental?", reply_markup=reply_markup)

async def ask_for_lorry_sale_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks user to select the lorry sale type when price is not known."""
    message = update.message or (update.callback_query.message if update.callback_query else None)
    
    keyboard = [
        [InlineKeyboardButton("Lorry Harga OTR", callback_data="lorry_sale_type_Lorry Price OTR")],
        [InlineKeyboardButton("Lorry harga Shj", callback_data="lorry_sale_type_Lorry harga Shj")],
        [InlineKeyboardButton("Offroad", callback_data="lorry_sale_type_Offroad")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=message.chat_id,
        text="What type of lorry sale is this?",
        reply_markup=reply_markup
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
    await message.reply_text(
        "Please choose the issuing company:", reply_markup=reply_markup
    )

async def ask_for_price_clarification(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks the user to clarify if a price is total or per piece."""
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    
    items_to_clarify = context.user_data.get('items_to_clarify', [])
    
    if not items_to_clarify:
        # All items clarified, proceed to the next step
        context.user_data['state'] = WAITING_FOR_COMPANY
        await check_and_transition(update, context)
        return

    # Pop the first item to clarify
    item_index, item = items_to_clarify.pop(0)
    
    desc = item['line_description']
    qty = item['qty']
    price = item['unit_price']
    
    question = (
        f"For the item:\n"
        f"'{desc}' (x{qty})\n"
        f"You entered a price of RM {price:,.2f}. Is this the TOTAL price for all {qty} items, or is it the price PER PIECE?"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("Total Price", callback_data=f"clarify_total_{item_index}"),
            InlineKeyboardButton("Price Per Piece", callback_data=f"clarify_perpiece_{item_index}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=message.chat_id, text=question, reply_markup=reply_markup
    )

async def ask_for_next_rental_fee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Asks the user about the next rental fee in the sequence.
    Manages the sub-flow for collecting rental fees like road tax, insurance, etc.
    """
    message = update.message or (update.callback_query.message if update.callback_query else None)
    
    # The list of fees to process
    if 'fees_to_ask' not in context.user_data:
        context.user_data['fees_to_ask'] = ['road_tax', 'insurance', 'sticker', 'agreement', 'puspakom']

    fees_to_ask = context.user_data['fees_to_ask']

    if not fees_to_ask:
        # All fees have been processed, move to the next step
        context.user_data['rental_fees_collected'] = True
        # Pre-select default equipment
        context.user_data['selected_equipment'] = ["LED Lighting", "Initial Service"]
        await show_equipment_checklist(update, context) # This is now imported from .logic
        return

    next_fee = fees_to_ask[0] # Peek at the next fee
    fee_name = next_fee.replace('_', ' ').title()

    keyboard = [
        [InlineKeyboardButton("Enter Price", callback_data=f"rental_price_{next_fee}")],
        [InlineKeyboardButton("Included in Package", callback_data=f"rental_included_{next_fee}")],
        [InlineKeyboardButton("Excluded", callback_data=f"rental_skip_{next_fee}")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await context.bot.send_message(
        chat_id=message.chat_id,
        text=f"What about {fee_name}?",
        reply_markup=reply_markup
    )


async def send_confirmation_message(update: Update, context: ContextTypes.DEFAULT_TYPE, is_review=False):
    """
    Sends a summary of the collected data for user confirmation/review.
    """
    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    
    confirmation_text = build_confirmation_text(context.user_data, is_review)

    if is_review:
        reply_markup = build_review_keyboard()
        context.user_data["state"] = REVIEWING_EXTRACTED_DATA
    else:
        reply_markup = build_confirm_generate_keyboard()
        context.user_data["state"] = CONFIRMING_DETAILS
        
    await context.bot.send_message(
        chat_id=message.chat_id, text=confirmation_text, reply_markup=reply_markup
    )

async def dispatch_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Dispatches the final payload to the API."""
    chat_id = update.effective_chat.id
    data = context.user_data
    doc_type = data.get("doc_type", "none")

    # Log the full user_data context for debugging
    logger.info("--- DISPATCHING REQUEST: FULL USER_DATA ---\n%s", json.dumps(data, indent=2, default=str))
    
    # Define prefixes for the new doc_no format
    doc_type_prefixes = {
        "sales": "SQ",
        "refurbish": "RQ",
        "rental": "RN"
    }
    prefix = doc_type_prefixes.get(doc_type, "QT") # Default to QT if type is unknown
    truck_num_part = data.get('truck_number', 'MISC').replace('/', '-')
    date_part = datetime.now().strftime('%d%m%y')
    
    
    # Ensure issuing_company is uppercase for lookup in COMPANY_ADDRESSES
    issuing_company_name = data.get("issuing_company", "Unique Enterprise").upper()

    payload = {
        "type": doc_type,
        "cust_code": "300-C0002",
        "cust_name": data.get("company_name", "CASH SALE"),
        "company_address": data.get("company_address", ""),
        "cust_contact": data.get("cust_contact", ""),
        "truck_number": data.get("truck_number", ""),
        "issuing_company": issuing_company_name,
        "doc_no": f"{prefix}-{truck_num_part}-{date_part}",
        "description": f"Quotation for truck {data.get('truck_number', '')}",
        "salesperson": data.get("salesperson")
    }
    
    # Common payload fields
    line_items = data.get("line_items", [])
    service_line_items = data.get("service_line_items", [])
    
    # Rental-specific logic to build line items
    if doc_type == "rental":
        if 'rental_amount' in data:
            rental_desc = "Monthly Rental"
            if data.get('rental_period_type') == 'daily':
                days = data.get('rental_days', 'N/A')
                start_date = data.get('rental_start_date', 'N/A')
                end_date = data.get('rental_end_date', 'N/A')
                rental_desc = f"{start_date} to {end_date} ({days} Days)"
            
            # Use a different key for the main rental amount to avoid confusion with other fees
            payload['main_rental_item'] = {"qty": 1, "line_description": rental_desc, "unit_price": data.get('rental_amount', 0), "gl_code": "535-000"}

        # Add other fixed fees to service_line_items
        if data.get('road_tax_amount') is not None:
            road_tax_amount = data.get('road_tax_amount', 0)
            road_tax_desc = "Road Tax (Included)" if road_tax_amount == 0 else "Road Tax (6mo)"
            service_line_items.append({"qty": 1, "line_description": road_tax_desc, "unit_price": road_tax_amount, "gl_code": "930-000"})
        if data.get('insurance_amount') is not None:
            insurance_amount = data.get('insurance_amount', 0)
            insurance_desc = "Insurance (Included)" if insurance_amount == 0 else "Insurance (6mo)"
            service_line_items.append({"qty": 1, "line_description": insurance_desc, "unit_price": insurance_amount, "gl_code": "931-000"})
        if data.get('sticker_amount') is not None:
            service_line_items.append({"qty": 1, "line_description": "Sticker", "unit_price": data.get('sticker_amount', 0), "gl_code": "501-000"})
        if data.get('agreement_amount') is not None:
            service_line_items.append({"qty": 1, "line_description": "Agreement Fee", "unit_price": data.get('agreement_amount', 0), "gl_code": "501-000"})
        if data.get('puspakom_amount') is not None:
            puspakom_amount = data.get('puspakom_amount', 0)
            puspakom_desc = "PUSPAKOM Fee (Included)" if puspakom_amount == 0 else "PUSPAKOM Fee"
            service_line_items.append({"qty": 1, "line_description": puspakom_desc, "unit_price": puspakom_amount, "gl_code": "930-000"}) # Assuming same GL code as road tax for now

        
        # Security deposit is not a line item, but should be displayed
        payload['security_deposit'] = data.get('security_deposit', 0)
        
        # Convert date objects to strings for the payload
        start_date_str = data.get("rental_start_date")
        if isinstance(start_date_str, date):
            start_date_str = start_date_str.strftime('%Y-%m-%d')
            
        end_date_str = data.get("rental_end_date")
        if isinstance(end_date_str, date):
            end_date_str = end_date_str.strftime('%Y-%m-%d')

        payload.update({
            "rental_period_type": data.get('rental_period_type', 'monthly'),
            "contract_period": data.get("contract_period"),
            "rental_start_date": start_date_str,
            "rental_end_date": end_date_str,
            "rental_days": data.get("rental_days", "N/A"),
            "deposit_condition": data.get('deposit_condition'),
            "deposit_amount": data.get('deposit_amount'),
            "selected_equipment": data.get("selected_equipment", []),
            "puspakom_amount": data.get("puspakom_amount"),
        })

    # Ensure all line items and service line items have a gl_code
    for item in line_items:
        if "gl_code" not in item:
            item["gl_code"] = get_gl_code_for_service(item["line_description"]) or "501-000" # Default GL code
    for item in service_line_items:
        if "gl_code" not in item:
            item["gl_code"] = get_gl_code_for_service(item["line_description"]) or "501-000" # Default GL code
    
    # --- New, more accurate Total Amount Calculation ---
    total_amount = 0
    # Add main lorry price for sales/refurbish
    total_amount += sum(float(item.get("unit_price", 0)) * item.get("qty", 1) for item in line_items)
    # Add all selected services for sales/refurbish
    total_amount += sum(float(item.get("unit_price", 0)) for item in service_line_items)

    # For rental, total is calculated differently
    if doc_type == "rental":
        main_rental_price = payload.get('main_rental_item', {}).get('unit_price', 0)
        # The service_line_items for rental are the fees (road tax, insurance, etc.)
        fees_total = sum(float(item.get("unit_price", 0)) for item in service_line_items)
        security_deposit = float(data.get('security_deposit') or 0)
        
        # The final total amount includes the security deposit
        total_amount = main_rental_price + fees_total + security_deposit

    payload.update({
        "body": data.get("body", ""),
        "line_items": line_items,
        "service_line_items": service_line_items,
        "included_services": data.get("included_services", []),
        "payment_phases": data.get("payment_phases", []),
        "total_amount": total_amount,
    })

    logger.info("--- DISPATCHING PAYLOAD ---\n%s", json.dumps(payload, indent=2, default=str))
    context.bot_data["last_payload"] = payload

    await context.bot.send_message(chat_id=chat_id, text=f"Generating PDF for {doc_type}...")
    try:
        response = requests.post(API_URL_LOCAL, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("success"):
            file_path = result.get("file_path")
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Generated PDF not found at {file_path}")
            
            await context.bot.send_message(chat_id=chat_id, text="PDF generated successfully! Sending it to you now...")
            with open(file_path, "rb") as pdf_file:
                await context.bot.send_document(chat_id=chat_id, document=pdf_file)
            
            context.user_data['state'] = POST_GENERATION
            await context.bot.send_message(chat_id=chat_id, text="✅ Done! You can now 'edit' these details, 'resend'/'redo' the PDF, or say 'new' to start over.")
        else:
            error_msg = result.get('detail', 'Unknown error')
            await context.bot.send_message(chat_id=chat_id, text=f"❌ API Error: {error_msg}\n\nYour data is saved. Try /start to retry.")
    except Exception as e:
        logger.exception("Unexpected error in dispatch_request")
        await context.bot.send_message(chat_id=chat_id, text=f"❌ Unexpected error: {str(e)}\n\nYour data is saved. Try /start to retry.")

async def check_and_transition(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    The central state machine that decides what information to ask for next.
    NEW FLOW: This is called AFTER doc_type is selected and AFTER customer check is done.
    """
    message = update.message or (update.callback_query.message if update.callback_query else None)
    data = context.user_data
    doc_type = data.get("doc_type")

    logger.info(
        f"check_and_transition | doc_type={doc_type} | "
        f"customer_checked={data.get('customer_checked')} | "
        f"state={data.get('state')}"
    )

    # Step 5: First, ensure we have a document type
    if not doc_type:
        context.user_data["state"] = AWAITING_DOC_TYPE
        await ask_for_doc_type(update, context)
        return
    
    # Step 6: Check if we've done the customer database check yet
    # NOTE: The following block is temporarily disabled due to ComServer integration issues.
    # if not data.get('customer_checked') and data.get('company_name'):
    #     await check_customer_in_database(update, context)
    #     return
    
    # As a fallback, we will treat every customer as new for now.
    data['is_new_customer'] = True
    data['customer_checked'] = True
    
    # --- New: Contextual Company Name Handling (after doc_type is known) ---
    if data.get('is_company_name_from_image_extracted') and data.get('extracted_image_company_name'):
        extracted_name = data['extracted_image_company_name']
        
        if doc_type == 'refurbish':
            # For refurbish, automatically use the name from the image
            data['company_name'] = extracted_name
            if 'extracted_image_company_address' in data:
                data['company_address'] = data['extracted_image_company_address']
            
            # Clean up temporary flags
            data.pop('is_company_name_from_image_extracted', None)
            data.pop('extracted_image_company_name', None)
            data.pop('extracted_image_company_address', None) # If address was extracted from image
            logger.info(f"Refurbish quote: Auto-using company name from image: {extracted_name}")
            # Recursively call check_and_transition to continue the flow
            await check_and_transition(update, context)
            return

        elif doc_type in ['sales', 'rental']:
            # For sales/rental, ask for confirmation
            context.user_data['state'] = AWAITING_COMPANY_NAME_CONFIRMATION
            keyboard = [
                [InlineKeyboardButton(f"Yes, use '{extracted_name}'", callback_data='confirm_company_name_yes')],
                [InlineKeyboardButton("No, enter new name", callback_data='confirm_company_name_no')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"I extracted a company name '{extracted_name}' from the image. Is this the customer's name for your {doc_type} quote?",
                reply_markup=reply_markup
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
    if doc_type in ["sales", "refurbish"]:
        required_fields.update({"body": "body type"})

    # Check each required field
    for field, prompt in required_fields.items():
        field_value = data.get(field)
        # A field is considered missing if it's None or an empty string.
        # "0" or "N/A" are now considered provided (though hidden on PDF).
        if not field_value:
            context.user_data["state"] = AWAITING_INFO
            context.user_data["waiting_for_field"] = field
            await context.bot.send_message(
                chat_id=message.chat_id, 
                text=missing_field_prompt(prompt)
            )
            return

    # All basic info collected! Now proceed to doc-specific flows
    if doc_type == "rental":
        rental_period_type = data.get('rental_period_type')
        if rental_period_type == 'daily':
            if not all(key in data for key in ['rental_start_date', 'rental_end_date', 'rental_amount', 'security_deposit']):
                await start_rental_flow(update, context)
                return
        elif rental_period_type == 'monthly':
            if not all(key in data for key in ['contract_period', 'rental_amount', 'security_deposit']):
                await start_rental_flow(update, context)
                return
        else: # If rental_period_type is not set at all
             await start_rental_flow(update, context)
             return
        
        # If we get here, all details for either daily or monthly are collected
        data['rental_details_collected'] = True
        
        # Now, check for fee/equipment steps if they haven't been done
        if not data.get('rental_fees_collected') or not data.get('rental_equipment_collected'):
             # This will trigger the ask_for_next_rental_fee -> show_equipment_checklist chain
             await ask_for_next_rental_fee(update, context)
             return
        
    elif doc_type == "sales":
        if not data.get("lorry_sale_item_created"):
            if data.get("line_items"):
                price = data["line_items"][0].get("unit_price", "N/A")
                message_text = f"I see the lorry price is RM {price}. Please clarify the description:"
                context.user_data["state"] = SELECTING_LORRY_SALE_TYPE
                keyboard = [
                    [InlineKeyboardButton("Lorry Price OTR", callback_data="clarify_sale_type_Lorry Price OTR")],
                    [InlineKeyboardButton("Lorry Harga SHJ", callback_data="clarify_sale_type_Lorry Harga SHJ")],
                    [InlineKeyboardButton("Offroad", callback_data="clarify_sale_type_Offroad")],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await message.reply_text(message_text, reply_markup=reply_markup)
            else:
                context.user_data["state"] = SELECTING_LORRY_SALE_TYPE
                await ask_for_lorry_sale_type(update, context)
            return
        
        if not data.get("services_priced"):
            context.user_data["state"] = SELECTING_SERVICES
            await show_services_checklist(update, context)
            return

        if not data.get("payment_phases_complete"):
            context.user_data["state"] = ASK_FOR_PAYMENT_PHASES
            keyboard = [
                [InlineKeyboardButton("Yes", callback_data='payment_phase_yes')],
                [InlineKeyboardButton("No", callback_data='payment_phase_no')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(
                chat_id=message.chat_id, 
                text="Do you want to add a phased payment schedule?", 
                reply_markup=reply_markup
            )
            return
            
    elif doc_type == "refurbish":
        if not data.get('line_items'):
            if data.get('waiting_for_field') == 'line_items' and message.text:
                from .helpers import parse_line_items_from_text
                parsed_items = parse_line_items_from_text(message.text)
                if parsed_items:
                    context.user_data['line_items'] = parsed_items
                    context.user_data['waiting_for_field'] = None # Reset
                else:
                    await context.bot.send_message(
                        chat_id=message.chat_id, 
                        text="I couldn't understand the line items. Please provide them in the format 'description - RM price' or 'qty x description - RM price' on separate lines."
                    )
                    return # Stay in current state to re-ask
            elif not data.get('line_items'):
                context.user_data['state'] = AWAITING_INFO
                context.user_data['waiting_for_field'] = 'line_items'
                await context.bot.send_message(
                    chat_id=message.chat_id, 
                    text="I need the line items for the refurbish quote (e.g., '1 unit rm10000' or 'description - RM price'). Please provide them."
                )
                return

    # Finally, ask for issuing company
    if not data.get("issuing_company"):
        context.user_data["state"] = WAITING_FOR_COMPANY
        await ask_for_issuing_company(update, context)
        return

    # Everything collected! Show final confirmation
    await send_confirmation_message(update, context, is_review=False)

async def show_equipment_checklist(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks the user to select equipment for the rental."""
    from .keyboards import build_equipment_keyboard # Local import
    context.user_data['state'] = SELECTING_EQUIPMENT
    reply_markup = build_equipment_keyboard(context.user_data.get('selected_equipment', []))
    message = update.message or (update.callback_query.message if update.callback_query else None)
    
    # If called from a callback, edit the message. Otherwise, send a new one.
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text="Please select the equipment provided:",
            reply_markup=reply_markup
        )
    else:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text="Please select the equipment provided:",
            reply_markup=reply_markup
        )
