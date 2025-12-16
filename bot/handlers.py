import logging
import os
import PIL.Image
from datetime import datetime
import telegram
import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from telegram.ext import ContextTypes

# Internal imports
from .constants import *
from .helpers import (
    validate_price, validate_phone_number, validate_truck_number, validate_date,
    get_gl_code_for_service, to_ordinal, search_customer_by_name, parse_line_items_from_text
)
from .ai import extract_details_from_text, extract_details_from_image
from .logic import (
    check_and_transition, send_confirmation_message, ask_for_doc_type, 
    ask_for_price_clarification, ask_for_issuing_company, show_services_checklist,
    start_rental_flow, ask_for_next_rental_fee, show_equipment_checklist
)
from .keyboards import build_edit_fields_keyboard, build_equipment_keyboard, build_contract_period_keyboard
from .templates import edit_field_prompt


logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command by clearing data and showing the main menu."""
    context.user_data.clear()
    # Reset the service menu path as well
    if 'service_menu_path' in context.user_data:
        del context.user_data['service_menu_path']
        
    await update.message.reply_text("Hello! I'm ready to create a new quote.")

async def reprint_log_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends the bot output log file to the user."""
    log_file = 'bot output.txt'
    try:
        with open(log_file, 'rb') as f:
            await context.bot.send_document(chat_id=update.effective_chat.id, document=InputFile(f, filename=log_file))
    except FileNotFoundError:
        await update.message.reply_text("Log file not found.")
    except Exception as e:
        await update.message.reply_text(f"An error occurred while sending the log file: {e}")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all incoming text messages, orchestrating the conversation flow."""
    user_text = update.message.text
    current_state = context.user_data.get("state", START)
    logger.info(f"handle_text: Current state: {current_state}, User text: {user_text}")

    if current_state == START:
        context.user_data.clear()
        # Check for explicit doc type in the initial message
        initial_text = user_text.lower()
        explicit_doc_type = None
        if "sales" in initial_text:
            explicit_doc_type = 'sales'
            user_text = user_text.replace("sales", "", 1)
        elif "rental" in initial_text:
            explicit_doc_type = 'rental'
            user_text = user_text.replace("rental", "", 1)
        elif "refurbish" in initial_text:
            explicit_doc_type = 'refurbish'
            user_text = user_text.replace("refurbish", "", 1)

        await update.message.reply_text("Analyzing your request...")
        details = await extract_details_from_text(user_text)
        if details.get("line_items"):
            for item in details["line_items"]:
                item["gl_code"] = get_gl_code_for_service(item["line_description"])
        
        # Prioritize explicit doc_type from initial text
        if explicit_doc_type:
            context.user_data['doc_type'] = explicit_doc_type

        for key, value in details.items():
            if value: context.user_data[key] = value
        await send_confirmation_message(update, context, is_review=True)
        return

    field_to_fill = context.user_data.get("waiting_for_field")

    if current_state == AWAITING_INFO and field_to_fill:
        is_valid, processed_value, error_message = True, user_text, ""

        if field_to_fill == "truck_number":
            is_valid, error_message = validate_truck_number(user_text)
            if is_valid: processed_value = user_text.strip().upper()
        elif field_to_fill == "cust_contact":
            is_valid, error_message = validate_phone_number(user_text)
            if is_valid: processed_value = user_text.strip()
        elif field_to_fill == 'line_items':
            parsed_items = parse_line_items_from_text(user_text)
            if not parsed_items:
                is_valid = False
                error_message = "I couldn't understand the line items. Please provide them in the format 'description - RM price' or 'qty x description - RM price'."
            else:
                for item in parsed_items:
                    item["gl_code"] = get_gl_code_for_service(item["line_description"])
                existing_items = context.user_data.get('line_items', [])
                processed_value = existing_items + parsed_items
        elif field_to_fill == 'rental_amount':
            is_valid, price, error_message = validate_price(user_text)
            if not is_valid:
                await update.message.reply_text(f"❌ {error_message}\n\nPlease provide the monthly rental amount again:")
                return
            context.user_data['rental_amount'] = price
            await update.message.reply_text(f"✅ Monthly rental set to RM {price:,.2f}.")
            context.user_data['state'] = AWAITING_INFO
            context.user_data['waiting_for_field'] = 'security_deposit'
            await update.message.reply_text("Now, please provide the Security Deposit amount:")
            return
        elif field_to_fill == 'security_deposit':
            is_valid, price, error_message = validate_price(user_text)
            if not is_valid:
                await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
                return
            context.user_data['security_deposit'] = price
            await update.message.reply_text(f"✅ Security deposit set to RM {price:,.2f}.")
            context.user_data.pop("waiting_for_field", None)
            await ask_for_next_rental_fee(update, context)
            return

        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        context.user_data[field_to_fill] = processed_value
        context.user_data.pop("waiting_for_field", None)
        await check_and_transition(update, context)
        return
    
    elif current_state == AWAITING_ADD_NEW_DETAIL_TYPE:
        if 'item' in user_text.lower():
            context.user_data['state'] = AWAITING_INFO
            context.user_data['waiting_for_field'] = 'line_items'
            await update.message.reply_text("Please provide the new line item(s) you'd like to add (e.g., 'description - RM price').")
        else:
            await update.message.reply_text("Sorry, I can only add 'items' for now. Please try again.")
        return

    elif current_state == WAITING_FOR_LORRY_PRICE:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return
        description = context.user_data.get("lorry_sale_description", "Lorry Sale")
        context.user_data["line_items"] = [{"qty": 1, "line_description": description, "unit_price": price, "gl_code": "500-000"}]
        context.user_data["lorry_sale_item_created"] = True
        await update.message.reply_text(f"✅ Lorry price set to RM {price:,.2f}")
        await check_and_transition(update, context)
        return

    elif current_state == EDITING_LORRY_PRICE:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        # Update the price in the first line item
        if context.user_data.get('line_items'):
            context.user_data['line_items'][0]['unit_price'] = price
            await update.message.reply_text(f"✅ Lorry price updated to RM {price:,.2f}.")
            
            # Reset payment phases if they exist
            if 'payment_phases' in context.user_data:
                del context.user_data['payment_phases']
                if 'payment_phases_complete' in context.user_data:
                    del context.user_data['payment_phases_complete']
                await update.message.reply_text("⚠️ The payment schedule has been reset due to the price change.")

        else:
            await update.message.reply_text("❌ Could not find lorry details to update.")

        # Return to the edit selection menu
        context.user_data['state'] = SELECTING_FIELD_TO_EDIT
        reply_markup = build_edit_fields_keyboard(context.user_data)
        await update.message.reply_text("You can edit another field or click 'Done Editing'.", reply_markup=reply_markup)
        return

    elif current_state == WAITING_FOR_PRICE:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return
        
        services_to_price = context.user_data.get("services_to_price", [])
        logger.info(f"WAITING_FOR_PRICE: services_to_price before pop: {services_to_price}")

        if not services_to_price: # Safety check for IndexError
            context.user_data["services_priced"] = True # Assume they've all been priced
            await update.message.reply_text("💡 All services were already priced. Moving on.")
            await check_and_transition(update, context)
            return

        current_service = services_to_price.pop(0)
        logger.info(f"WAITING_FOR_PRICE: Popped '{current_service}'. Remaining services: {services_to_price}")
        
        # Create and store the service line item
        if 'temp_service_line_items' not in context.user_data:
            context.user_data['temp_service_line_items'] = []
        
        new_service_item = {
            "qty": 1,
            "line_description": current_service,
            "unit_price": price,
            "gl_code": get_gl_code_for_service(current_service)
        }
        context.user_data['temp_service_line_items'].append(new_service_item)
        await update.message.reply_text(f"✅ Price for '{current_service}' set to RM {price:,.2f}")

        # Check if there are more services to price
        if services_to_price:
            await update.message.reply_text(f"Please provide the price for: {services_to_price[0]}")
        else:
            # All services are priced, finalize this step
            existing_services = context.user_data.get("service_line_items", [])
            context.user_data["service_line_items"] = existing_services + context.user_data.get("temp_service_line_items", [])
            context.user_data.pop("temp_service_line_items", None)
            context.user_data["services_priced"] = True
            await update.message.reply_text("✅ All service prices have been recorded.")
            await check_and_transition(update, context)
        return

    elif current_state == COLLECTING_PHASE_AMOUNT:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return
        
        counter = context.user_data.get('payment_phase_counter', 1)
        phase_name = f"{to_ordinal(counter)} Payment"
        
        context.user_data.get('payment_phases', []).append({'name': phase_name, 'amount': price})
        context.user_data['payment_phase_counter'] = counter + 1
        
        await update.message.reply_text(f"✅ {phase_name} of RM {price:,.2f} added.")
        
        from .keyboards import build_payment_phase_keyboard
        reply_markup = build_payment_phase_keyboard()
        await update.message.reply_text("What would you like to do next?", reply_markup=reply_markup)
        return

    elif current_state == EDITING_FIELD:
        field_to_edit = context.user_data.pop("editing_field", None)
        if not field_to_edit:
            await update.message.reply_text("An error occurred. Please start over.")
            return await start_command(update, context)

        is_valid, processed_value, error_message = True, user_text, ""

        # Apply validation based on the field being edited
        if field_to_edit == "truck_number":
            is_valid, error_message = validate_truck_number(user_text)
            if is_valid: processed_value = user_text.strip().upper()
        elif field_to_edit == "cust_contact":
            is_valid, error_message = validate_phone_number(user_text)
            if is_valid: processed_value = user_text.strip()
        elif field_to_edit in ['rental_amount', 'security_deposit', 'road_tax_amount', 'insurance_amount', 'sticker_amount']:
            is_valid, price, error_message = validate_price(user_text)
            if is_valid: processed_value = price

        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            # Put the editing field back so the user can retry
            context.user_data["editing_field"] = field_to_edit
            return

        # Update the data
        context.user_data[field_to_edit] = processed_value
        await update.message.reply_text(f"✅ '{field_to_edit.replace('_', ' ').title()}' updated successfully.")

        # Return to the edit selection menu
        context.user_data['state'] = SELECTING_FIELD_TO_EDIT
        reply_markup = build_edit_fields_keyboard(context.user_data)
        await update.message.reply_text("You can edit another field or click 'Done Editing'.", reply_markup=reply_markup)
        return

    elif current_state in [WAITING_FOR_ROAD_TAX_PRICE, WAITING_FOR_INSURANCE_PRICE, WAITING_FOR_STICKER_PRICE]:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return
        if current_state == WAITING_FOR_ROAD_TAX_PRICE:
            context.user_data['road_tax_amount'] = price
        elif current_state == WAITING_FOR_INSURANCE_PRICE:
            context.user_data['insurance_amount'] = price
        elif current_state == WAITING_FOR_STICKER_PRICE:
            context.user_data['sticker_amount'] = price
        
        if 'fees_to_ask' in context.user_data and context.user_data['fees_to_ask']:
            context.user_data['fees_to_ask'].pop(0)
            
        await update.message.reply_text(f"✅ Price set to RM {price:,.2f}.")
        await ask_for_next_rental_fee(update, context)
        return

    elif current_state == WAITING_FOR_RENTAL_START_DATE:
        is_valid, date_obj, error_message = validate_date(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease provide the start date again:")
            return
        
        context.user_data['rental_start_date'] = date_obj
        context.user_data['state'] = WAITING_FOR_RENTAL_END_DATE
        await update.message.reply_text("✅ Start date set. Now, please provide the Rental End Date (YYYY-MM-DD):")
        return

    elif current_state == WAITING_FOR_RENTAL_END_DATE:
        is_valid, date_obj, error_message = validate_date(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease provide the end date again:")
            return
        
        context.user_data['rental_end_date'] = date_obj
        await update.message.reply_text("✅ End date set.")
        
        # Calculate rental days
        start_date = context.user_data['rental_start_date']
        end_date = context.user_data['rental_end_date']
        rental_days = (end_date - start_date).days + 1
        context.user_data['rental_days'] = rental_days

        # Now ask for the TOTAL rental amount
        context.user_data['state'] = AWAITING_INFO
        context.user_data['waiting_for_field'] = 'rental_amount'
        await update.message.reply_text(f"Please provide the TOTAL Rental Amount for {rental_days} days:")
        return

    elif current_state == WAITING_FOR_AGREEMENT_PRICE:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease provide the Agreement Fee again:")
            return
        context.user_data['agreement_amount'] = price
        await update.message.reply_text(f"✅ Agreement Fee set to RM {price:,.2f}.")
        context.user_data['fees_to_ask'].pop(0) # Pop 'agreement' from the fees_to_ask list
        await ask_for_next_rental_fee(update, context)
        return

    elif current_state == POST_GENERATION:
        if "edit" in user_text.lower():
            context.user_data['state'] = SELECTING_FIELD_TO_EDIT
            reply_markup = build_edit_fields_keyboard(context.user_data)
            await update.message.reply_text("Which field would you like to edit?", reply_markup=reply_markup)
        elif "redo" in user_text.lower() or "resend" in user_text.lower() or "again" in user_text.lower():
            await update.message.reply_text("Resending the last generated PDF...")
            from .logic import dispatch_request
            await dispatch_request(update, context)
        elif "new" in user_text.lower() or "start over" in user_text.lower():
            await start_command(update, context)
        else:
            await update.message.reply_text("I didn't understand that. You can say 'edit' (to modify details), 'resend' or 'redo' (to get the PDF again), or 'new' (to start over).")
        return

    elif current_state == WAITING_FOR_CUSTOM_SERVICE_NAME:
        new_service_name = user_text.strip()
        if 'selected_services' not in context.user_data:
            context.user_data['selected_services'] = []
        context.user_data['selected_services'].append(new_service_name)
        context.user_data['state'] = SELECTING_SERVICES
        # We need to use query.message for show_services_checklist
        # A bit of a hack: we'll just call it without the query object
        await update.message.reply_text(f"✅ Added '{new_service_name}' to the list.")
        await show_services_checklist(update, context)
        return

    else:
        await check_and_transition(update, context)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles incoming photos, extracting details and adding them to the current context."""
    await update.message.reply_text("Analyzing the image... 📄")
    photo_file = await update.message.photo[-1].get_file()
    photo_path = await photo_file.download_to_drive()
    try:
        with PIL.Image.open(photo_path) as img:
            details = await extract_details_from_image(img)
            logger.info("--- EXTRACTED DETAILS FROM IMAGE --- \n%s", json.dumps(details, indent=2, default=str))
            if not details:
                await update.message.reply_text("Sorry, I couldn't understand the image. Please provide details manually.")
                return
            if details.get("line_items"):
                for item in details["line_items"]:
                    item["gl_code"] = get_gl_code_for_service(item["line_description"])
            
            # Store image-extracted company name separately for contextual handling
            if details.get('company_name'):
                context.user_data['extracted_image_company_name'] = details['company_name']
                context.user_data['is_company_name_from_image_extracted'] = True
                # NO LONGER CLEARING details['company_name'] here. Let it propagate.

            for key, value in details.items():
                if value:
                    context.user_data[key] = value
            await send_confirmation_message(update, context, is_review=True)
    finally:
        if os.path.exists(str(photo_path)):
            os.remove(str(photo_path))

async def review_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Yes, Continue' and 'No, I need to edit' buttons."""
    query = update.callback_query
    await query.answer()
    if query.data == 'review_correct':
        await query.edit_message_text(text="Details confirmed. Checking for any other missing information...")
        await check_and_transition(update, context)
    elif query.data == 'review_edit':
        context.user_data['state'] = SELECTING_FIELD_TO_EDIT
        reply_markup = build_edit_fields_keyboard(context.user_data)
        await query.edit_message_text("Which field would you like to edit?", reply_markup=reply_markup)


async def edit_selection_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the selection of a field to edit."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'edit_done' or data == 'remove_done':
        await query.edit_message_text(text="Finished editing. Let's review again.")
        await send_confirmation_message(update, context, is_review=True)
        return

    if data == 'edit_remove_line_items':
        context.user_data['state'] = SELECTING_ITEM_TO_REMOVE
        from .keyboards import build_remove_items_keyboard
        reply_markup = build_remove_items_keyboard(context.user_data)
        await query.edit_message_text("Select an item to remove:", reply_markup=reply_markup)
        return

    if data == 'edit_lorry_price':
        context.user_data['state'] = EDITING_LORRY_PRICE
        await query.edit_message_text(text="Please provide the new price for the lorry.")
        return

    if data == 'edit_payment_phases':
        context.user_data['payment_phases'] = []
        context.user_data['payment_phase_counter'] = 1
        await query.edit_message_text(text="Let's re-enter the payment schedule from scratch.\n\nPlease provide the amount for the 1st Payment:")
        context.user_data['state'] = COLLECTING_PHASE_AMOUNT
        return

    if data == 'edit_line_items':
        # Clear existing line items and re-ask
        if 'line_items' in context.user_data:
            del context.user_data['line_items']
        context.user_data['state'] = AWAITING_INFO
        context.user_data['waiting_for_field'] = 'line_items'
        await query.edit_message_text(text="Please provide the new line items for the refurbish quote (e.g., 'description - RM price').")
        return

    if data == 'edit_rental_equipment':
        # Clear existing equipment and restart the selection process
        if 'selected_equipment' in context.user_data:
            del context.user_data['selected_equipment']
        if 'rental_equipment_collected' in context.user_data:
            del context.user_data['rental_equipment_collected']
        await show_equipment_checklist(update, context)
        return

    if data == 'edit_services':
        # Clear all service-related data to restart the flow
        for key in ['selected_services', 'services_to_price', 'service_line_items', 'services_priced']:
            if key in context.user_data:
                del context.user_data[key]
        
        # Reset the service menu path to the root
        context.user_data['service_menu_path'] = []
        await show_services_checklist(update, context)
        return

    field_to_edit = data.replace("edit_", "")
    context.user_data["state"] = EDITING_FIELD
    context.user_data["editing_field"] = field_to_edit
    await query.edit_message_text(text=edit_field_prompt(field_to_edit))

async def final_confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the final confirmation keyboard: Generate, Edit, or Add."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'final_confirm_generate':
        await query.edit_message_text(text="Confirmed. Generating PDF...")
        from .logic import dispatch_request
        await dispatch_request(update, context)
    
    elif data == 'final_confirm_edit':
        context.user_data['state'] = SELECTING_FIELD_TO_EDIT
        reply_markup = build_edit_fields_keyboard(context.user_data)
        await query.edit_message_text("Which field would you like to edit?", reply_markup=reply_markup)

    elif data == 'final_confirm_add_new':
        keyboard = [
            [InlineKeyboardButton("Add Line Item", callback_data='add_new_line_item')],
            [InlineKeyboardButton("Add Service", callback_data='add_new_service')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("What would you like to add?", reply_markup=reply_markup)
        # We don't set a state here, we let the next callback handle it.


async def customer_flow_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith('select_matched_customer_'):
        matched_name = data.replace('select_matched_customer_', '')
        context.user_data['matched_customer_name'] = matched_name
        data = 'use_existing_customer'
    if data == 'use_existing_customer':
        matched_name = context.user_data.get('matched_customer_name')
        if not matched_name:
            await query.edit_message_text("An error occurred, please try again.")
            return
        customer_details = await search_customer_by_name(matched_name)
        if customer_details and matched_name in customer_details:
            customer_data = customer_details[matched_name]
            context.user_data.update({'company_name': customer_data.get('name'), 'company_address': customer_data.get('address'), 'cust_contact': customer_data.get('contact'), 'is_new_customer': False})
            await query.edit_message_text(f"Existing data for '{matched_name}' loaded. Proceeding...")
        else:
            await query.edit_message_text(f"Could not retrieve details for '{matched_name}'. Using current data.")
        context.user_data['customer_checked'] = True
        context.user_data['customer_selected'] = True
        await check_and_transition(update, context)
    elif data == 'use_extracted_data':
        context.user_data['is_new_customer'] = True
        context.user_data['customer_checked'] = True
        context.user_data['customer_selected'] = True
        await query.edit_message_text("Understood. Using the provided data as a new customer entry.")
        await check_and_transition(update, context)

async def price_clarification_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    action = data[1]
    item_index = int(data[2])
    item = context.user_data['line_items'][item_index]
    if action == 'total':
        item['unit_price'] = item['unit_price'] / item['qty']
    await query.edit_message_text(f"✅ Understood. Price for '{item['line_description']}' set to RM {item['unit_price']:.2f} per piece.")
    await ask_for_price_clarification(update, context)

async def service_checklist_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all callbacks from the service checklist keyboard."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Initialize path and selections if they don't exist
    category_path = context.user_data.get('service_menu_path', [])
    selected_services = context.user_data.get("selected_services", [])

    if data == "service_done":
        # Finalize selection and move to pricing
        if not selected_services:
            await query.edit_message_text(text="No services selected.")
            context.user_data["services_priced"] = True
        else:
            context.user_data["services_to_price"] = selected_services
            context.user_data["temp_service_line_items"] = []
            context.user_data["state"] = WAITING_FOR_PRICE
            await query.edit_message_text(text=f"Please provide the price for: {selected_services[0]}")
        return

    elif data.startswith("category_"):
        if data == "category_back":
            if category_path:
                category_path.pop()
        else:
            category_name = data.replace("category_", "")
            category_path.append(category_name)
        
        context.user_data['service_menu_path'] = category_path

    elif data.startswith("service_"):
        service_name = data.replace("service_", "").strip()

        if service_name == "Others":
            context.user_data['state'] = WAITING_FOR_CUSTOM_SERVICE_NAME
            await query.edit_message_text(text="Please provide the name for the new service:")
            return
        
        if service_name in selected_services:
            selected_services.remove(service_name)
        else:
            selected_services.append(service_name)
        context.user_data["selected_services"] = selected_services

    # After any action, show the updated checklist
    await show_services_checklist(update, context)
    return

async def clarify_sale_type_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    description = query.data.replace("clarify_sale_type_", "")
    if context.user_data.get("line_items"):
        context.user_data["line_items"][0]["line_description"] = description
        context.user_data["lorry_sale_item_created"] = True
        await query.edit_message_text(text=f"Description set to: {description}.")
        await check_and_transition(update, context)
    else: await query.edit_message_text(text="Something went wrong. Let's try again with /start.")

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("company_"):
        company_name = data.replace("company_", "")
        context.user_data["issuing_company"] = company_name.upper() # Convert to uppercase
        await query.edit_message_text(text=f"Selected issuing company: {company_name}")
        await check_and_transition(update, context)

async def lorry_sale_type_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    description = query.data.replace("lorry_sale_type_", "")
    context.user_data["lorry_sale_description"] = description
    context.user_data["state"] = WAITING_FOR_LORRY_PRICE
    await query.edit_message_text(text=f"{description}. Now, please provide the price for the lorry.")

async def payment_phase_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == 'payment_phase_yes':
        context.user_data['payment_phases'] = []
        context.user_data['payment_phase_counter'] = 1
        await query.edit_message_text(text="Please provide the amount for the 1st Payment:")
        context.user_data['state'] = COLLECTING_PHASE_AMOUNT
    elif data == 'payment_phase_add_another':
        counter = context.user_data.get('payment_phase_counter', 1)
        ordinal = to_ordinal(counter)
        context.user_data['state'] = COLLECTING_PHASE_AMOUNT
        await query.edit_message_text(text=f"Please provide the amount for the {ordinal} Payment:")
    elif data == 'payment_phase_calculate_balance':
        total_items = sum(item.get("unit_price", 0) for item in context.user_data.get("line_items", []))
        total_services = sum(item.get("unit_price", 0) for item in context.user_data.get("service_line_items", []))
        total_quote_amount = total_items + total_services
        paid_amount = sum(phase.get("amount", 0) for phase in context.user_data.get("payment_phases", []))
        balance = total_quote_amount - paid_amount
        context.user_data.get("payment_phases", []).append({'name': 'Final Payment', 'amount': balance})
        context.user_data['payment_phases_complete'] = True
        await query.edit_message_text(text=f"Final balance of RM {balance:.2f} calculated and added.")
        await check_and_transition(update, context)
    elif data == 'payment_phase_no':
        context.user_data['payment_phases_complete'] = True
        await query.edit_message_text(text="No payment schedule will be added.")
        await check_and_transition(update, context)

async def contract_period_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    period = query.data.replace("contract_period_", "")
    if period == 'others':
        context.user_data['state'] = AWAITING_INFO
        context.user_data['waiting_for_field'] = 'contract_period'
        await query.edit_message_text(text="Please specify the contract period:")
    else:
        context.user_data['contract_period'] = period
        context.user_data['state'] = AWAITING_INFO
        context.user_data['waiting_for_field'] = 'rental_amount'
        await query.edit_message_text(text=f"Contract period set to {period}. Now, please provide the monthly rental amount:")

async def rental_fee_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, action, fee_type = query.data.split('_', 2)
    fee_key = f"{fee_type}_amount"
    if action == "price":
        if fee_type == 'puspakom':
            context.user_data['puspakom_amount'] = 350.0
            await query.edit_message_text(text=f"✅ PUSPAKOM Fee set to RM 350.00.")
            if 'fees_to_ask' in context.user_data and context.user_data['fees_to_ask']:
                context.user_data['fees_to_ask'].pop(0)
            await ask_for_next_rental_fee(update, context)
            return

        if fee_type == 'road_tax': context.user_data['state'] = WAITING_FOR_ROAD_TAX_PRICE
        elif fee_type == 'insurance': context.user_data['state'] = WAITING_FOR_INSURANCE_PRICE
        elif fee_type == 'sticker': context.user_data['state'] = WAITING_FOR_STICKER_PRICE
        elif fee_type == 'agreement':
            context.user_data['agreement_amount'] = 500.0 # Default price for agreement fee
            context.user_data['state'] = WAITING_FOR_AGREEMENT_PRICE
        await query.edit_message_text(text=f"Please enter the price for {fee_type.replace('_', ' ').title()}:")
    else:
        if fee_type == 'agreement': # Included/Skip for Agreement Fee
            context.user_data['agreement_amount'] = 0 if action == "included" else None
        else: # Existing fees
            context.user_data[fee_key] = 0 if action == "included" else None
        await query.edit_message_text(text=f"✅ {fee_type.replace('_', ' ').title()} will be marked as '{action}'.")
        if 'fees_to_ask' in context.user_data and context.user_data['fees_to_ask']: context.user_data['fees_to_ask'].pop(0)
        await ask_for_next_rental_fee(update, context)

async def rental_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("rental_period_"):
        period = data.replace("rental_period_", "")
        context.user_data['rental_period_type'] = period
        if period == 'daily':
            context.user_data['state'] = WAITING_FOR_RENTAL_START_DATE
            await query.edit_message_text(text="Please provide the Rental Start Date (YYYY-MM-DD):")
        else:
            reply_markup = build_contract_period_keyboard()
            await query.edit_message_text(text="Please select the contract period:", reply_markup=reply_markup)
    elif data.startswith("rental_equip_"):
        if data == "rental_equip_done":
            context.user_data['rental_equipment_collected'] = True
            await query.edit_message_text(text="All rental details collected.")
            await check_and_transition(update, context)
            return
        item_name = data.replace("rental_equip_", "")
        selected_equipment = context.user_data.get('selected_equipment', [])
        if item_name in selected_equipment: selected_equipment.remove(item_name)
        else: selected_equipment.append(item_name)
        context.user_data['selected_equipment'] = selected_equipment
        reply_markup = build_equipment_keyboard(selected_equipment)
        await query.edit_message_reply_markup(reply_markup=reply_markup)

async def master_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A single entry point for all callback queries."""
    query = update.callback_query
    data = query.data
    
    if data.startswith("doc_type_"):
        await doc_type_callback_handler(update, context)
    elif data.startswith("review_"):
        await review_callback_handler(update, context)
    elif data.startswith("edit_") or data == "remove_done":
        await edit_selection_callback_handler(update, context)
    elif data.startswith("use_") or data.startswith("select_matched_customer_"):
        await customer_flow_callback_handler(update, context)
    elif data.startswith("clarify_"):
        if data.startswith("clarify_sale_type_"):
            await clarify_sale_type_callback_handler(update, context)
        else:
            await price_clarification_callback_handler(update, context)
    elif data.startswith("service_") or data.startswith("category_"):
        await service_checklist_callback_handler(update, context)
    elif data.startswith("lorry_sale_type_"):
        await lorry_sale_type_callback_handler(update, context)
    elif data.startswith("payment_phase_"):
        await payment_phase_callback_handler(update, context)
    elif data.startswith("contract_period_"):
        await contract_period_callback_handler(update, context)
    elif data.startswith("rental_price_") or data.startswith("rental_included_") or data.startswith("rental_skip_"):
        await rental_fee_callback_handler(update, context)
    elif data.startswith("rental_"):
        await rental_callback_handler(update, context)
    elif data.startswith("company_"):
        await button_callback_handler(update, context)
    elif data.startswith("final_confirm_"):
        await final_confirmation_handler(update, context)
    elif data.startswith("add_new_"):
        await add_new_detail_callback_handler(update, context)
    elif data.startswith("confirm_company_name_"): # New callback handler
        await confirm_company_name_callback_handler(update, context)
    elif data.startswith("remove_item_"):
        await remove_items_callback_handler(update, context)
    else:
        # Fallback or default handler if needed
        logger.warning(f"Unhandled callback query with data: {data}")
        await query.answer("This button seems to be unhandled.")
        
async def doc_type_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    doc_type = query.data.replace("doc_type_", "")
    context.user_data["doc_type"] = doc_type
    await query.edit_message_text(text=f"Selected quote type: {doc_type.capitalize()}.")
    await check_and_transition(update, context)

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
async def add_new_detail_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the 'Add Line Item' and 'Add Service' buttons."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'add_new_line_item':
        context.user_data['state'] = AWAITING_INFO
        context.user_data['waiting_for_field'] = 'line_items'
        await query.edit_message_text("Please provide the new line item(s) you'd like to add (e.g., 'description - RM price').")
    
    elif data == 'add_new_service':
        # Clear existing service pricing data to restart that part of the flow
        for key in ['services_to_price', 'temp_service_line_items', 'services_priced']:
            if key in context.user_data:
                del context.user_data[key]
        
        context.user_data['state'] = SELECTING_SERVICES
        # We need to use query.message for show_services_checklist, but we have a query
        # so we will call it with the query's message
        await show_services_checklist(update, context)

async def confirm_company_name_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Clean up flags first, before calling check_and_transition
    extracted_name_to_confirm = context.user_data.pop('extracted_image_company_name', None)
    context.user_data.pop('is_company_name_from_image_extracted', None)
    # Also pop any extracted address/contact that came with the image if we decide not to use them
    extracted_address = context.user_data.pop('extracted_image_company_address', None) # If we decide to store it separately
    extracted_contact = context.user_data.pop('extracted_image_cust_contact', None) # If we decide to store it separately


    if data == 'confirm_company_name_yes':
        # The correct name and address are already in user_data from handle_photo.
        # We just need to confirm and proceed.
        await query.edit_message_text(text=f"✅ Confirmed customer name: '{context.user_data.get('company_name', '')}'. Proceeding...")
    
    elif data == 'confirm_company_name_no':
        # Clear the main company_name and address (if they were populated by the image)
        context.user_data.pop('company_name', None) 
        context.user_data.pop('company_address', None)
        context.user_data.pop('cust_contact', None)

        await query.edit_message_text(text="Okay, please provide the customer's company name:")
        context.user_data['state'] = AWAITING_INFO
        context.user_data['waiting_for_field'] = 'company_name'
        return # Return immediately as check_and_transition will be called in handle_text
    
    await check_and_transition(update, context)

async def remove_items_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the removal of a line item."""
    query = update.callback_query
    await query.answer()
    
    parts = query.data.split('_')
    item_type = '_'.join(parts[2:-1])
    item_index = int(parts[-1])
    
    removed_item_desc = ""
    
    if item_type == 'main_item':
        if 'line_items' in context.user_data and len(context.user_data['line_items']) > item_index:
            removed_item_desc = context.user_data['line_items'].pop(item_index).get('line_description', '')
    
    elif item_type == 'service_item':
        if 'service_line_items' in context.user_data and len(context.user_data['service_line_items']) > item_index:
            removed_item_desc = context.user_data['service_line_items'].pop(item_index).get('line_description', '')
            
    elif item_type == 'main_rental_item':
        if 'main_rental_item' in context.user_data:
            removed_item_desc = context.user_data.pop('main_rental_item').get('line_description', '')

    from .keyboards import build_remove_items_keyboard # Local import to avoid circular dependency
    reply_markup = build_remove_items_keyboard(context.user_data)
    await query.edit_message_text(
        text=f"Removed '{removed_item_desc}'. Select another item to remove or click 'Done'.",
        reply_markup=reply_markup
    )