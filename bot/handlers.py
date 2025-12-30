import logging
import os
import PIL.Image
from datetime import datetime
import telegram
import json
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, InputFile
from telegram.ext import ContextTypes
import copy

# Internal imports
from .constants import *
from .helpers import (
    validate_price,
    validate_phone_number,
    validate_truck_number,
    validate_date,
    get_gl_code_for_service,
    to_ordinal,
    search_customer_by_name,
    parse_line_items_from_text,
)
from .ai import (
    extract_details_from_text,
    extract_text_from_image,
    extract_line_items_from_text,
)
from .logic import (
    check_and_transition,
    send_confirmation_message,
    ask_for_doc_type,
    ask_for_price_clarification,
    ask_for_issuing_company,
    show_main_services,
    start_rental_flow,
    ask_for_next_rental_fee,
    show_equipment_checklist,
    dispatch_request,
    show_additional_services,
    ask_for_line_item_review,
    ask_for_service_review,
    ask_for_payment_phase_review,
    rebuild_rental_fee_items,
    recalculate_final_payment,
)
from .keyboards import (
    build_edit_fields_keyboard,
    build_equipment_keyboard,
    build_contract_period_keyboard,
    build_remove_items_keyboard,
    build_field_edit_options_keyboard,
    build_post_generation_keyboard,
    build_main_services_keyboard,
    build_tukar_nama_keyboard,
    build_puspakom_keyboard,
    build_road_tax_keyboard,
    build_insurance_keyboard,
    build_additional_services_keyboard,
    build_skip_keyboard,
    build_edit_payment_schedule_keyboard,
    build_edit_payment_phase_options_keyboard,
    build_line_item_field_edit_keyboard,
    build_line_item_review_keyboard,
    build_additional_services_subcategory_keyboard,
    build_additional_services_items_keyboard,
)
from .templates import edit_field_prompt


logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the /start command by clearing data and showing the main menu."""
    context.user_data.clear()
    context.user_data.pop("issuing_company", None)
    if "service_menu_path" in context.user_data:
        del context.user_data["service_menu_path"]
    if "state_history" in context.user_data:
        del context.user_data["state_history"]

    message = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    if message:
        await message.reply_text(
            'Hello! I\'m ready to create a new quote.\n\nType "Sales", "Refurbish", or "Rental" to start a specific quote.\nOR\nSend a picture of a document/vehicle to extract details automatically.'
        )
    else:
        logger.error("Could not find a message to reply to in start_command.")


async def reprint_log_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Sends the bot output log file to the user."""
    log_file = "bot output.txt"
    try:
        with open(log_file, "rb") as f:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=InputFile(f, filename=log_file),
            )
    except FileNotFoundError:
        await update.message.reply_text("Log file not found.")
    except Exception as e:
        await update.message.reply_text(
            f"An error occurred while sending the log file: {e}"
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles all incoming text messages, orchestrating the conversation flow."""
    user_text = update.message.text
    current_state = context.user_data.get("state", START)

    # Readable state mapping for logs
    state_names = {
        v: k for k, v in globals().items() if isinstance(v, int) and k.isupper()
    }
    readable_state = state_names.get(current_state, str(current_state))

    logger.info(f"handle_text: Current state: {readable_state}, User text: {user_text}")

    # Push current state to history if different from last
    state_history = context.user_data.get("state_history", [])
    if not state_history or state_history[-1] != current_state:
        state_history.append(current_state)
    context.user_data["state_history"] = state_history

    if current_state == START:
        context.user_data.clear()
        context.user_data.pop("issuing_company", None)
        initial_text = user_text.lower()
        explicit_doc_type = None
        if "sales" in initial_text:
            explicit_doc_type = "sales"
            user_text = user_text.replace("sales", "", 1)
        elif "rental" in initial_text:
            explicit_doc_type = "rental"
            user_text = user_text.replace("rental", "", 1)
        elif "refurbish" in initial_text:
            explicit_doc_type = "refurbish"
            user_text = user_text.replace("refurbish", "", 1)

        await update.message.reply_text("Analyzing your request...")
        details = await extract_details_from_text(user_text)
        if details.get("line_items"):
            for item in details["line_items"]:
                # Robust key mapping
                if "description" in item and "line_description" not in item:
                    item["line_description"] = item.pop("description")
                if "quantity" in item and "qty" not in item:
                    item["qty"] = item.pop("quantity")

                desc = item.get("line_description")
                if desc:
                    item["gl_code"] = get_gl_code_for_service(desc)

        if explicit_doc_type:
            context.user_data["doc_type"] = explicit_doc_type

        for key, value in details.items():
            if value:
                context.user_data[key] = value
        await send_confirmation_message(update, context, is_review=True)
        return

    if current_state == WAITING_FOR_CUSTOM_EQUIPMENT:
        equipment_name = user_text.strip()
        if equipment_name:
            selected_equipment = context.user_data.get("selected_equipment", [])
            if equipment_name not in selected_equipment:
                selected_equipment.append(equipment_name)
            context.user_data["selected_equipment"] = selected_equipment
            await update.message.reply_text(f"'{equipment_name}' added to equipment.")
            # Re-show the equipment list with the new item selected
            await show_equipment_checklist(update, context)
        else:
            await update.message.reply_text(
                "Equipment name cannot be empty. Please try again."
            )
        return

    field_to_fill = context.user_data.get("waiting_for_field")

    if current_state == AWAITING_INFO and field_to_fill:
        is_valid, processed_value, error_message = True, user_text, ""

        if field_to_fill == "truck_number":
            is_valid, error_message = validate_truck_number(user_text)
            if is_valid:
                processed_value = user_text.strip().upper()
        elif field_to_fill == "cust_contact":
            is_valid, error_message = validate_phone_number(user_text)
            if is_valid:
                processed_value = user_text.strip()
        elif field_to_fill in [
            "rental_amount",
            "security_deposit",
            "road_tax_amount",
            "insurance_amount",
            "sticker_amount",
            "agreement_amount",
            "puspakom_amount",
        ]:
            is_valid, price, error_message = validate_price(user_text)
            if not is_valid:
                await update.message.reply_text(
                    f"❌ {error_message}\n\nPlease try again:"
                )
                return
            context.user_data[field_to_fill] = price

            # Check if we are just editing a single value (not in the initial collection flow)
            # If fees_to_ask is empty, we are likely editing.
            if context.user_data.get(
                "rental_fees_collected"
            ) and not context.user_data.get("fees_to_ask"):
                # Manually trigger a silent rebuild of the fee items
                rebuild_rental_fee_items(context)

                # Now force state back to edit menu
                context.user_data["state"] = SELECTING_FIELD_TO_EDIT
                context.user_data.pop("waiting_for_field", None)
                reply_markup = build_edit_fields_keyboard(context.user_data)
                await update.message.reply_text(
                    f"✅ {field_to_fill.replace('_', ' ').title()} updated to RM {price:,.2f}. Returning to menu.",
                    reply_markup=reply_markup,
                )
                return

            if field_to_fill == "rental_amount":
                context.user_data["waiting_for_field"] = "security_deposit"
                await update.message.reply_text(
                    f"✅ Rental amount set to RM {price:,.2f}. Now, please provide the security deposit amount:"
                )
                return
            elif field_to_fill == "security_deposit":
                # Normal flow falls through to check_and_transition
                processed_value = price
            else:
                # Should not happen in normal flow if fees_to_ask is working,
                # but if it does, just fall through.
                processed_value = price
        elif field_to_fill == "line_items":
            parsed_items = await extract_line_items_from_text(
                user_text
            )  # Use the new AI function
            if not parsed_items:
                is_valid = False
                error_message = "I couldn't understand the line items. Please provide them again, for example: '1 unit New Lorry - RM 150000'."
            else:
                for item in parsed_items:
                    if isinstance(item, dict) and "line_description" in item:
                        item["gl_code"] = get_gl_code_for_service(
                            item["line_description"]
                        )
                    else:
                        logger.warning(f"AI returned a malformed line item: {item}")
                        continue  # Skip this malformed item

                # Append to existing items instead of replacing
                existing_items = context.user_data.get("line_items", [])

                # Filter out valid new items
                new_valid_items = [
                    item for item in parsed_items if isinstance(item, dict)
                ]

                # Combine lists
                context.user_data["line_items"] = existing_items + new_valid_items

                context.user_data.pop("waiting_for_field", None)

                # Instead of going to the edit menu, go to the line item review
                await ask_for_line_item_review(update, context)
                return

        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        context.user_data[field_to_fill] = processed_value
        context.user_data.pop("waiting_for_field", None)
        await check_and_transition(update, context)
        return

    if current_state == EDITING_FIELD:
        field_to_edit = context.user_data.pop("editing_field", None)
        if not field_to_edit:
            await update.message.reply_text("An error occurred. Please start over.")
            return await start_command(update, context)

        is_valid, processed_value, error_message = True, user_text, ""

        if field_to_edit == "truck_number":
            is_valid, error_message = validate_truck_number(user_text)
            if is_valid:
                processed_value = user_text.strip().upper()
        elif field_to_edit == "cust_contact":
            is_valid, error_message = validate_phone_number(user_text)
            if is_valid:
                processed_value = user_text.strip()
        elif field_to_edit == "rental_start_date":
            is_valid, date_obj, error_message = validate_date(user_text)
            if is_valid:
                processed_value = date_obj.strftime("%Y-%m-%d")
                if "rental_end_date" in context.user_data:
                    start_date = date_obj
                    end_date = datetime.strptime(
                        context.user_data["rental_end_date"], "%Y-%m-%d"
                    ).date()
                    context.user_data["rental_days"] = (end_date - start_date).days
        elif field_to_edit == "rental_end_date":
            is_valid, date_obj, error_message = validate_date(user_text)
            if is_valid:
                processed_value = date_obj.strftime("%Y-%m-%d")
                if "rental_start_date" in context.user_data:
                    end_date = date_obj
                    start_date = datetime.strptime(
                        context.user_data["rental_start_date"], "%Y-%m-%d"
                    ).date()
                    context.user_data["rental_days"] = (end_date - start_date).days
        elif field_to_edit in [
            "rental_amount",
            "security_deposit",
            "road_tax_amount",
            "insurance_amount",
            "sticker_amount",
            "agreement_amount",
            "puspakom_amount",
        ]:
            is_valid, price, error_message = validate_price(user_text)
            if is_valid:
                processed_value = price

        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            context.user_data["editing_field"] = field_to_edit
            return

        context.user_data[field_to_edit] = processed_value
        await update.message.reply_text(
            f"✅ '{field_to_edit.replace('_', ' ').title()}' updated."
        )

        context.user_data.pop("temp_editing_field", None)
        context.user_data["state"] = SELECTING_FIELD_TO_EDIT
        reply_markup = build_edit_fields_keyboard(context.user_data)
        await update.message.reply_text(
            "You can edit another field or click 'Done Editing'.",
            reply_markup=reply_markup,
        )
        return

    if current_state == WAITING_FOR_LORRY_PRICE:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        description = context.user_data.get("lorry_sale_description", "Lorry")

        # Create the line item
        new_item = {
            "qty": 1,
            "line_description": description,
            "unit_price": price,
            "gl_code": get_gl_code_for_service(description),
        }

        # Add to existing line items
        line_items = context.user_data.get("line_items", [])
        line_items.append(new_item)
        context.user_data["line_items"] = line_items

        context.user_data["lorry_sale_item_created"] = True
        await update.message.reply_text(f"✅ Lorry price set to RM {price:,.2f}.")

        # Reset state and continue the flow
        context.user_data["state"] = START
        await check_and_transition(update, context)
        return

    if current_state == AWAITING_ADDITIONAL_SERVICE_PRICE:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        service_name = context.user_data.get("awaiting_price_for_additional_service")
        if not service_name:
            await update.message.reply_text("An error occurred. Please start over.")
            return await start_command(update, context)

        # Add new service
        new_service_item = {
            "qty": 1,
            "line_description": service_name,
            "unit_price": price,
            "gl_code": get_gl_code_for_service(service_name),
        }

        service_line_items = context.user_data.get("service_line_items", [])
        service_line_items.append(new_service_item)
        context.user_data["service_line_items"] = service_line_items

        await update.message.reply_text(
            f"✅ Service '{service_name}' added with price RM {price:,.2f}."
        )

        # Re-show the items menu for the current category/sub-category
        category = context.user_data.get("current_additional_category")
        sub_category = context.user_data.get("current_additional_sub_category")

        if not category:
            # Fallback if context lost
            context.user_data["state"] = SELECTING_ADDITIONAL_CATEGORY
            reply_markup = build_additional_services_keyboard(context.user_data)
            await update.message.reply_text(
                "Service added. Please select a category to continue:",
                reply_markup=reply_markup,
            )
            return

        skip_menu_subcats = [
            "Body Repairs",
            "Aircond",
            "Wiring",
            "Tyre Botak Tukar",
            "Service",
        ]
        if sub_category in skip_menu_subcats:
            # Return to Sub-Category Menu (Level 2)
            reply_markup = build_additional_services_subcategory_keyboard(
                category, context.user_data
            )
            await update.message.reply_text(
                f"Select more services for {category}:", reply_markup=reply_markup
            )
            return

        context.user_data["state"] = SELECTING_ADDITIONAL_SUB_SERVICE
        # Pass None for sub_category if it wasn't set (direct list case)
        # But wait, build_additional_services_items_keyboard handles the logic.
        # If we are here, we must know if it's a sub-category or not.
        # Check logic.py logic again? No, we check structure.

        # Actually, simpler: if sub_category is None, pass None.
        reply_markup = build_additional_services_items_keyboard(
            category, sub_category, context.user_data
        )

        label = sub_category if sub_category else category
        await update.message.reply_text(
            f"Select more services for {label} or go back:", reply_markup=reply_markup
        )
        return

    if current_state == AWAITING_CUSTOM_ADDITIONAL_SERVICE_NAME:
        service_name = user_text.strip()
        if not service_name:
            await update.message.reply_text(
                "Service name cannot be empty. Please try again:"
            )
            return

        context.user_data["awaiting_price_for_additional_service"] = service_name
        context.user_data["state"] = AWAITING_ADDITIONAL_SERVICE_PRICE
        await update.message.reply_text(
            f"Please provide the price for '{service_name}':"
        )
        return

    if current_state == COLLECTING_PHASE_AMOUNT:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        counter = context.user_data.get("payment_phase_counter", 1)
        ordinal = to_ordinal(counter)

        phases = context.user_data.get("payment_phases", [])
        phases.append({"name": f"{ordinal} Payment", "amount": price, "remarks": ""})
        context.user_data["payment_phases"] = phases

        context.user_data["state"] = AWAITING_PAYMENT_PHASE_REMARKS
        reply_markup = build_skip_keyboard()
        await update.message.reply_text(
            f"✅ {ordinal} payment of RM {price:,.2f} added. Any remarks for this payment? (Optional, press Skip to leave blank)",
            reply_markup=reply_markup,
        )
        return

    if current_state == AWAITING_PAYMENT_PHASE_REMARKS:
        remarks = user_text.strip()
        phases = context.user_data.get("payment_phases", [])
        if phases:
            phases[-1]["remarks"] = remarks

        await update.message.reply_text("✅ Remarks added.")

        context.user_data["payment_phase_counter"] += 1

        # Recalculate to ensure ordering (1st, 2nd... Final)
        recalculate_final_payment(context.user_data)

        # Redirect to the review/edit menu instead of the 'What next' question
        await ask_for_payment_phase_review(update, context)
        return

    if current_state == EDITING_PAYMENT_PHASE_AMOUNT:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        phase_index = context.user_data.pop("editing_payment_phase_index", None)
        if phase_index is None:
            await update.message.reply_text("An error occurred. Please start over.")
            return await start_command(update, context)

        phases = context.user_data.get("payment_phases", [])
        phases[phase_index]["amount"] = price

        # Recalculate Final Payment after edit
        recalculate_final_payment(context.user_data)

        await update.message.reply_text("✅ Amount updated and balance recalculated.")
        await ask_for_payment_phase_review(update, context)  # Return to review menu
        return

    if current_state == EDITING_PAYMENT_PHASE_REMARKS:
        remarks = user_text.strip()
        phase_index = context.user_data.pop("editing_payment_phase_index", None)
        if phase_index is None:
            await update.message.reply_text("An error occurred. Please start over.")
            return await start_command(update, context)

        phases = context.user_data.get("payment_phases", [])
        phases[phase_index]["remarks"] = remarks

        # Recalculate Final Payment after edit
        recalculate_final_payment(context.user_data)

        await update.message.reply_text("✅ Remarks updated.")
        await ask_for_payment_phase_review(update, context)  # Return to review menu
        return

    if current_state == WAITING_FOR_RENTAL_START_DATE:
        is_valid, date_obj, error_message = validate_date(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        context.user_data["rental_start_date"] = date_obj.strftime("%Y-%m-%d")
        context.user_data["state"] = WAITING_FOR_RENTAL_END_DATE
        await update.message.reply_text(
            "✅ Start date noted. Now, please provide the Rental End Date (YYYY-MM-DD):"
        )
        return

    if current_state == WAITING_FOR_RENTAL_END_DATE:
        is_valid, date_obj, error_message = validate_date(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        context.user_data["rental_end_date"] = date_obj.strftime("%Y-%m-%d")
        context.user_data["state"] = AWAITING_INFO
        context.user_data["waiting_for_field"] = "rental_amount"
        await update.message.reply_text(
            "✅ End date noted. Now, please provide the rental amount:"
        )
        return

    if current_state == WAITING_FOR_CONTRACT_PERIOD:
        context.user_data["contract_period"] = user_text
        context.user_data["state"] = AWAITING_INFO
        context.user_data["waiting_for_field"] = "rental_amount"
        await update.message.reply_text(
            f"✅ Contract period set to {user_text}. Now, please provide the monthly rental amount:"
        )
        return

    if current_state == EDITING_SERVICE_PRICE:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        service_name = context.user_data.pop("editing_service", None)
        if not service_name:
            await update.message.reply_text("An error occurred. Please start over.")
            return await start_command(update, context)

        # Update the price in the relevant list
        found_and_updated = False
        for item_list in ["service_line_items", "temp_service_line_items"]:
            for item in context.user_data.get(item_list, []):
                if item["line_description"] == service_name:
                    item["unit_price"] = price
                    found_and_updated = True
                    break
            if found_and_updated:
                break

        await update.message.reply_text(
            f"✅ Price for '{service_name}' updated to RM {price:,.2f}."
        )

        await ask_for_service_review(update, context)  # Return to review menu
        return

    if current_state == AWAITING_SUB_SERVICE_PRICE:
        is_valid, price, error_message = validate_price(user_text)
        if not is_valid:
            await update.message.reply_text(f"❌ {error_message}\n\nPlease try again:")
            return

        service_name = context.user_data.pop("awaiting_price_for_service", None)
        if not service_name:
            await update.message.reply_text("An error occurred. Please start over.")
            return await start_command(update, context)

        # Remove previous selection for the same main service
        from services_config import SALES_SERVICES

        main_service_selection = context.user_data.get("main_service_selection")
        if main_service_selection:
            sub_services_to_remove = SALES_SERVICES.get(main_service_selection, [])

            service_line_items = context.user_data.get("service_line_items", [])
            service_line_items = [
                item
                for item in service_line_items
                if item.get("line_description") not in sub_services_to_remove
            ]
            context.user_data["service_line_items"] = service_line_items

        # Add new service
        new_service_item = {
            "qty": 1,
            "line_description": service_name,
            "unit_price": price,
            "gl_code": get_gl_code_for_service(service_name),
        }

        context.user_data.get("service_line_items", []).append(new_service_item)

        await update.message.reply_text(
            f"✅ Service '{service_name}' added with price RM {price:,.2f}."
        )

        context.user_data["state"] = SELECTING_MAIN_SERVICE
        context.user_data.pop("main_service_selection", None)
        reply_markup = build_main_services_keyboard(context.user_data)
        await update.message.reply_text(
            "Please select another main service or click 'Done'.",
            reply_markup=reply_markup,
        )
        return

    if current_state == SELECTING_FIELD_TO_EDIT:
        await update.message.reply_text(
            "Please use the buttons to edit fields or click 'Done Editing'."
        )
        return

    if current_state == REVIEWING_LINE_ITEMS:
        # Handle text input during line item review (e.g., editing a field)
        editing_item_index = context.user_data.get("editing_line_item_index")
        editing_field = context.user_data.get("editing_line_item_field")

        if editing_item_index is not None and editing_field:
            line_items = context.user_data.get("line_items", [])
            if 0 <= editing_item_index < len(line_items):
                item = line_items[editing_item_index]
                if editing_field == "description":
                    item["description"] = user_text
                elif editing_field == "qty":
                    try:
                        item["qty"] = int(user_text)
                    except ValueError:
                        await update.message.reply_text(
                            "Invalid quantity. Please enter a number."
                        )
                        return
                elif editing_field == "unit_price":
                    is_valid, price, error_message = validate_price(user_text)
                    if not is_valid:
                        await update.message.reply_text(
                            f"❌ {error_message}\n\nPlease try again:"
                        )
                        return
                    item["unit_price"] = price

                context.user_data.pop("editing_line_item_index")
                context.user_data.pop("editing_line_item_field")
                await update.message.reply_text("✅ Item updated.")
                await ask_for_line_item_review(update, context)
                return

    # Fallback for unhandled text, transition to check_and_transition
    await check_and_transition(update, context)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    analyzing_msg = await update.message.reply_text("Analyzing the image... 📄")
    context.user_data["confirmation_message_id"] = analyzing_msg.message_id
    photo_file = await update.message.photo[-1].get_file()
    photo_path = await photo_file.download_to_drive()
    try:
        with PIL.Image.open(photo_path) as img:
            extracted_text = await extract_text_from_image(
                img
            )  # Call the correct function
            if not extracted_text:
                await update.message.reply_text(
                    "Sorry, I couldn't extract text from the image. Please provide details manually."
                )
                return

            # Now extract details from the text
            details = await extract_details_from_text(extracted_text)
            logger.info(
                "--- EXTRACTED DETAILS FROM IMAGE --- \n%s",
                json.dumps(details, indent=2, default=str),
            )
            if not details:
                await update.message.reply_text(
                    "Sorry, I couldn't understand the extracted text. Please provide details manually."
                )
                return
            if details.get("line_items"):
                for item in details["line_items"]:
                    # Robust key mapping
                    if "description" in item and "line_description" not in item:
                        item["line_description"] = item.pop("description")
                    if "quantity" in item and "qty" not in item:
                        item["qty"] = item.pop("quantity")

                    desc = item.get("line_description")
                    if desc:
                        item["gl_code"] = get_gl_code_for_service(desc)

            for key, value in details.items():
                if value:
                    context.user_data[key] = value

            # If it's a rental quote, ensure extracted fees are rebuilt into line items
            if str(context.user_data.get("doc_type")).startswith("rental"):
                rebuild_rental_fee_items(context)

            await send_confirmation_message(update, context, is_review=True)
    finally:
        if os.path.exists(str(photo_path)):
            os.remove(str(photo_path))


async def review_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "review_correct":
        await query.edit_message_text(
            text="Details confirmed. Checking for any other missing information..."
        )
        await check_and_transition(update, context)
    elif query.data == "review_edit":
        context.user_data["state"] = SELECTING_FIELD_TO_EDIT
        reply_markup = build_edit_fields_keyboard(context.user_data)
        await query.edit_message_text(
            "Which field would you like to edit?", reply_markup=reply_markup
        )


async def edit_selection_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "edit_done":
        await query.edit_message_text(text="✅ Finished editing.")
        context.user_data.pop("confirmation_message_id", None)
        await send_confirmation_message(update, context, is_review=False)
        return

    field_to_edit = data.replace("edit_", "")

    if field_to_edit == "payment_phases":
        # Redirect to new review function
        await ask_for_payment_phase_review(update, context)
        return

    if field_to_edit == "rental_start_date":
        context.user_data["state"] = EDITING_FIELD
        context.user_data["editing_field"] = "rental_start_date"
        await query.edit_message_text(
            text="Please provide the new Rental Start Date (YYYY-MM-DD):"
        )
        return

    if field_to_edit == "rental_end_date":
        context.user_data["state"] = EDITING_FIELD
        context.user_data["editing_field"] = "rental_end_date"
        await query.edit_message_text(
            text="Please provide the new Rental End Date (YYYY-MM-DD):"
        )
        return

    if field_to_edit == "contract_period":
        reply_markup = build_contract_period_keyboard()
        await query.edit_message_text(
            text="Please select the new contract period:", reply_markup=reply_markup
        )
        return

    if field_to_edit in [
        "road_tax_amount",
        "insurance_amount",
        "sticker_amount",
        "agreement_amount",
        "puspakom_amount",
    ]:
        fee_name = field_to_edit.replace("_amount", "")
        context.user_data["fees_to_ask"] = [fee_name]
        await ask_for_next_rental_fee(update, context, fee_to_ask=fee_name)
        return

    if field_to_edit == "services":
        # Redirect to new review function
        await ask_for_service_review(update, context)
        return

    if field_to_edit == "line_items":
        # Redirect to line item review function
        await ask_for_line_item_review(update, context)
        return

    if field_to_edit == "issuing_company":
        await ask_for_issuing_company(update, context)
        return

    if field_to_edit == "rental_equipment":
        await show_equipment_checklist(update, context)
        return

    # Handle special direct edit actions that don't need the options menu
    if data == "edit_remove_line_items":
        context.user_data["state"] = SELECTING_ITEM_TO_REMOVE
        reply_markup = build_remove_items_keyboard(context.user_data)
        await query.edit_message_text(
            "Select an item to remove:", reply_markup=reply_markup
        )
        return

    context.user_data["temp_editing_field"] = field_to_edit  # Use temp field

    reply_markup = build_field_edit_options_keyboard(field_to_edit)
    await query.edit_message_text(
        f"What would you like to do with '{field_to_edit.replace('_', ' ').title()}'?",
        reply_markup=reply_markup,
    )


async def field_edit_options_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles the options (Edit Value, Remove Field, Back) for editing a specific field."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Extract the base field name, regardless of 'edit_value_' or 'remove_field_' prefix
    field_to_edit = data.replace("edit_value_", "").replace("remove_field_", "")

    if data.startswith("edit_value_"):
        # Set state to await new value
        context.user_data["state"] = EDITING_FIELD
        context.user_data["editing_field"] = field_to_edit
        await query.edit_message_text(text=edit_field_prompt(field_to_edit))

    elif data.startswith("remove_field_"):
        if field_to_edit in context.user_data:
            del context.user_data[field_to_edit]

            # If removing a rental fee, trigger rebuild
            if field_to_edit in [
                "road_tax_amount",
                "insurance_amount",
                "sticker_amount",
                "agreement_amount",
                "puspakom_amount",
            ]:
                context.user_data["rental_fees_collected"] = False
                context.user_data["fees_to_ask"] = []
                await query.edit_message_text(
                    text=f"✅ Field '{field_to_edit.replace('_', ' ').title()}' removed. Recalculating rental fees..."
                )
                # Send updated confirmation
                await send_confirmation_message(update, context, is_review=False)
                # Trigger fee rebuild
                await ask_for_next_rental_fee(update, context)
                return

            await query.edit_message_text(
                text=f"✅ Field '{field_to_edit.replace('_', ' ').title()}' removed."
            )

            # Send fresh confirmation message
            await send_confirmation_message(update, context, is_review=False)

            # Return to main edit menu
            context.user_data["state"] = SELECTING_FIELD_TO_EDIT
            from .keyboards import build_edit_fields_keyboard

            reply_markup = build_edit_fields_keyboard(context.user_data)
            await query.message.reply_text(
                "You can edit another field or click 'Done Editing'.",
                reply_markup=reply_markup,
            )
        else:
            await query.edit_message_text(
                text=f"🤔 Field '{field_to_edit.replace('_', ' ').title()}' was already empty or not found."
            )
            # Return to main edit menu
            context.user_data["state"] = SELECTING_FIELD_TO_EDIT
            from .keyboards import build_edit_fields_keyboard

            reply_markup = build_edit_fields_keyboard(context.user_data)
            await query.message.reply_text(
                "You can edit another field or click 'Done Editing'.",
                reply_markup=reply_markup,
            )

    elif data == "edit_done":  # Back to Edit Menu
        context.user_data["state"] = SELECTING_FIELD_TO_EDIT
        from .keyboards import build_edit_fields_keyboard

        reply_markup = build_edit_fields_keyboard(context.user_data)
        await query.edit_message_text(
            "Which field would you like to edit?", reply_markup=reply_markup
        )


async def main_service_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data.replace("main_service_", "")

    state_history = context.user_data.get("state_history", [])
    state_history.append(context.user_data.get("state"))
    context.user_data["state_history"] = state_history

    if data == "tukar_nama":
        context.user_data["state"] = SELECTING_SUB_SERVICE
        context.user_data["main_service_selection"] = "Tukar Nama"
        reply_markup = build_tukar_nama_keyboard(context.user_data)
        await query.edit_message_text(
            "Please select a 'Tukar Nama' option:", reply_markup=reply_markup
        )
    elif data == "puspakom":
        context.user_data["state"] = SELECTING_SUB_SERVICE
        context.user_data["main_service_selection"] = "Puspakom"
        reply_markup = build_puspakom_keyboard(context.user_data)
        await query.edit_message_text(
            "Please select a 'Puspakom' option:", reply_markup=reply_markup
        )
    elif data == "road_tax":
        context.user_data["state"] = SELECTING_SUB_SERVICE
        context.user_data["main_service_selection"] = "Road Tax"
        reply_markup = build_road_tax_keyboard(context.user_data)
        await query.edit_message_text(
            "Please select a 'Road Tax' option:", reply_markup=reply_markup
        )
    elif data == "insurance":
        context.user_data["state"] = SELECTING_SUB_SERVICE
        context.user_data["main_service_selection"] = "Insurance"
        reply_markup = build_insurance_keyboard(context.user_data)
        await query.edit_message_text(
            "Please select an 'Insurance' option:", reply_markup=reply_markup
        )
    elif data == "additional":
        # Fallback if accessed somehow, though button removed
        context.user_data["state"] = SELECTING_ADDITIONAL_SERVICES
        reply_markup = build_additional_services_keyboard(context.user_data)
        await query.edit_message_text(
            "Please select additional services:", reply_markup=reply_markup
        )
    elif data == "done":
        context.user_data["main_services_done"] = True

        if context.user_data.pop("adding_service_from_review", False):
            await ask_for_service_review(update, context)
            return

        # Check if any additional services are selected
        from services_config import ADDITIONAL_SERVICES

        has_additional = False
        current_services = [
            item["line_description"]
            for item in context.user_data.get("service_line_items", [])
        ]

        # Helper to flatten additional services
        all_additional_items = []
        for cat_val in ADDITIONAL_SERVICES.values():
            if isinstance(cat_val, list):
                all_additional_items.extend(cat_val)
            elif isinstance(cat_val, dict):
                for sub_list in cat_val.values():
                    if isinstance(sub_list, list):
                        all_additional_items.extend(sub_list)

        # Check intersection
        if any(item in all_additional_items for item in current_services):
            has_additional = True

        if has_additional:
            # Proceed to payment
            context.user_data["additional_services_done"] = True
            context.user_data["state"] = ASK_FOR_PAYMENT_PHASES
            keyboard = [
                [InlineKeyboardButton("Yes", callback_data="payment_phase_yes")],
                [InlineKeyboardButton("No", callback_data="payment_phase_no")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "Do you want to add a phased payment schedule?",
                reply_markup=reply_markup,
            )
        else:
            # Send to additional services
            context.user_data["state"] = SELECTING_ADDITIONAL_CATEGORY
            await show_additional_services(update, context)

    elif data == "back":  # From sub-menus to main services
        state_history = context.user_data.get("state_history", [])
        if state_history:
            previous_state = state_history.pop()
            context.user_data["state"] = previous_state
        await check_and_transition(update, context)


async def sub_service_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data.replace("sub_service_", "")

    state_history = context.user_data.get("state_history", [])
    state_history.append(context.user_data.get("state"))
    context.user_data["state_history"] = state_history

    context.user_data["awaiting_price_for_service"] = data
    context.user_data["state"] = AWAITING_SUB_SERVICE_PRICE
    await query.edit_message_text(f"Please provide the price for '{data}':")


async def additional_service_navigation_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data

    from services_config import ADDITIONAL_SERVICES

    # 0. Done with Additional Services
    if data == "additional_done":
        if context.user_data.pop("adding_service_from_review", False):
            await ask_for_service_review(update, context)
            return

        context.user_data["additional_services_done"] = True
        context.user_data["state"] = ASK_FOR_PAYMENT_PHASES
        keyboard = [
            [InlineKeyboardButton("Yes", callback_data="payment_phase_yes")],
            [InlineKeyboardButton("No", callback_data="payment_phase_no")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Do you want to add a phased payment schedule?",
            reply_markup=reply_markup,
        )
        return

    # 1. Back to Main Categories
    if data == "additional_category_back":
        context.user_data["state"] = SELECTING_ADDITIONAL_CATEGORY
        reply_markup = build_additional_services_keyboard(context.user_data)
        await query.edit_message_text(
            "Please select a category:", reply_markup=reply_markup
        )
        return

    # 2. Select Category (Level 1 -> Level 2/3 or Item)
    if data.startswith("additional_category_"):
        category = data.replace("additional_category_", "")

        # SPECIAL CASE: Other Services
        if category == "Other Services":
            context.user_data["additional_custom_parent_context"] = None
            context.user_data["state"] = AWAITING_CUSTOM_ADDITIONAL_SERVICE_NAME
            await query.edit_message_text(
                "Please provide the name for the custom service:"
            )
            return

        context.user_data["current_additional_category"] = category
        content = ADDITIONAL_SERVICES.get(category)

        if isinstance(content, list):
            # Direct list. Check optimization: Single item matching category?
            if len(content) == 1 and content[0] == category:
                item_name = content[0]
                service_line_items = context.user_data.get("service_line_items", [])
                item_exists = any(
                    item["line_description"] == item_name for item in service_line_items
                )

                if item_exists:
                    # Toggle Off
                    context.user_data["service_line_items"] = [
                        i
                        for i in service_line_items
                        if i["line_description"] != item_name
                    ]
                    await query.edit_message_text(
                        f"Removed '{item_name}' from services."
                    )
                    # Return to Category Menu
                    reply_markup = build_additional_services_keyboard(context.user_data)
                    await query.edit_message_reply_markup(reply_markup=reply_markup)
                else:
                    # Pricing
                    context.user_data["awaiting_price_for_additional_service"] = (
                        item_name
                    )
                    context.user_data["state"] = AWAITING_ADDITIONAL_SERVICE_PRICE
                    await query.edit_message_text(
                        f"Please provide the price for '{item_name}':"
                    )
                return

            # Normal List
            reply_markup = build_additional_services_items_keyboard(
                category, None, context.user_data
            )
            await query.edit_message_text(
                f"Select services for {category}:", reply_markup=reply_markup
            )
        else:
            # Sub-categories dict
            reply_markup = build_additional_services_subcategory_keyboard(
                category, context.user_data
            )
            await query.edit_message_text(
                f"Select a sub-category for {category}:", reply_markup=reply_markup
            )
        return
    # 3. Select Sub-Category (Level 2 -> Level 3 or Item)
    if data.startswith("additional_sub_"):
        sub_category = data.replace("additional_sub_", "")
        category = context.user_data.get("current_additional_category")
        if not category:
            context.user_data["state"] = SELECTING_ADDITIONAL_CATEGORY
            reply_markup = build_additional_services_keyboard(context.user_data)
            await query.edit_message_text(
                "Context lost. Please select a category:", reply_markup=reply_markup
            )
            return

        context.user_data["current_additional_sub_category"] = sub_category

        items = ADDITIONAL_SERVICES.get(category, {}).get(sub_category, [])
        skip_menu_subcats = [
            "Body Repairs",
            "Aircond",
            "Wiring",
            "Tyre Botak Tukar",
            "Service",
        ]

        # Check optimization: Single item matching sub-category OR explicit skip list
        if sub_category in skip_menu_subcats or (
            len(items) == 1 and items[0] == sub_category
        ):
            item_name = items[0] if items else sub_category
            service_line_items = context.user_data.get("service_line_items", [])
            item_exists = any(
                item["line_description"] == item_name for item in service_line_items
            )

            if item_exists:
                # Toggle Off
                context.user_data["service_line_items"] = [
                    i for i in service_line_items if i["line_description"] != item_name
                ]
                await query.edit_message_text(f"Removed '{item_name}' from services.")
                # Return to Sub-Category Menu (Level 2) - showing list of add-ons/body works
                reply_markup = build_additional_services_subcategory_keyboard(
                    category, context.user_data
                )
                await query.edit_message_reply_markup(reply_markup=reply_markup)
            else:
                # Pricing
                context.user_data["awaiting_price_for_additional_service"] = item_name
                context.user_data["state"] = AWAITING_ADDITIONAL_SERVICE_PRICE
                await query.edit_message_text(
                    f"Please provide the price for '{item_name}':"
                )
            return

        # Normal Items List
        reply_markup = build_additional_services_items_keyboard(
            category, sub_category, context.user_data
        )
        await query.edit_message_text(
            f"Select services for {sub_category}:", reply_markup=reply_markup
        )
        return

    # 4. Select Item (Level 3 -> Pricing or Toggle Off)
    if data.startswith("additional_item_"):
        item_name = data.replace("additional_item_", "")
        service_line_items = context.user_data.get("service_line_items", [])

        item_exists = any(
            item["line_description"] == item_name for item in service_line_items
        )

        if item_exists:
            context.user_data["service_line_items"] = [
                item
                for item in service_line_items
                if item["line_description"] != item_name
            ]
            await query.edit_message_text(f"Removed '{item_name}' from services.")
            # Return to Items Menu (Level 3)
            category = context.user_data.get("current_additional_category")
            sub_category = context.user_data.get("current_additional_sub_category")
            reply_markup = build_additional_services_items_keyboard(
                category, sub_category, context.user_data
            )
            await query.edit_message_reply_markup(reply_markup=reply_markup)
        else:
            context.user_data["awaiting_price_for_additional_service"] = item_name
            context.user_data["state"] = AWAITING_ADDITIONAL_SERVICE_PRICE
            await query.edit_message_text(
                f"Please provide the price for '{item_name}':"
            )
        return

    # 5. Add Other (Level 3 -> Custom Name)
    if data.startswith("additional_other_"):
        parts = data.split("_")
        if len(parts) >= 3:  # Handle 'additional_other_Label'
            context.user_data["additional_custom_parent_context"] = parts[2]
        else:
            context.user_data["additional_custom_parent_context"] = None

        context.user_data["state"] = AWAITING_CUSTOM_ADDITIONAL_SERVICE_NAME
        await query.edit_message_text("Please provide the name for the custom service:")
        return


async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("company_"):
        company_name = data.replace("company_", "")
        context.user_data["issuing_company"] = company_name.upper()
        logger.info(f"Company selected: {company_name.upper()}")

        await query.edit_message_text(
            text=f"✅ Selected issuing company: {company_name}"
        )
        context.user_data.pop("confirmation_message_id", None)
        context.user_data.pop("company_selection_message_id", None)
        logger.info("Company selection complete, transitioning...")
        await check_and_transition(update, context)


async def final_confirmation_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles the final confirmation keyboard: Generate, Edit, or Add."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "final_confirm_generate":
        await query.edit_message_text(text="Confirmed. Generating PDF...")
        await dispatch_request(update, context)

    elif data == "final_confirm_proforma":
        is_proforma_display = context.user_data.get("is_proforma_display", False)
        context.user_data["is_proforma_display"] = not is_proforma_display
        await send_confirmation_message(update, context, is_review=False)

    elif data == "final_confirm_edit":
        context.user_data["state"] = SELECTING_FIELD_TO_EDIT
        reply_markup = build_edit_fields_keyboard(context.user_data)
        await query.edit_message_text(
            "Which field would you like to edit?", reply_markup=reply_markup
        )

    elif data == "final_confirm_add_new":
        # This can be expanded with more options
        keyboard = [
            [InlineKeyboardButton("Add Line Item", callback_data="add_new_line_item")],
            [
                InlineKeyboardButton("Add Service", callback_data="add_new_service")
            ],  # New option to add service
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "What would you like to add?", reply_markup=reply_markup
        )


async def add_new_detail_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles adding new details like line items after initial confirmation."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "add_new_line_item":
        context.user_data["state"] = AWAITING_INFO
        context.user_data["waiting_for_field"] = "line_items"
        await query.edit_message_text(
            "Please provide the new line item(s) you'd like to add (e.g., 'description - RM price')."
        )
    elif data == "add_new_service":
        context.user_data["state"] = SELECTING_MAIN_SERVICE
        context.user_data["adding_service_from_review"] = True
        reply_markup = build_main_services_keyboard(context.user_data)
        await query.edit_message_text(
            "Please select a main service to add:", reply_markup=reply_markup
        )


async def lorry_sale_type_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    description = query.data.replace("lorry_sale_type_", "")
    context.user_data["lorry_sale_description"] = description
    context.user_data["state"] = WAITING_FOR_LORRY_PRICE
    await query.edit_message_text(
        text=f"{description}. Now, please provide the price for the lorry."
    )


async def payment_phase_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data == "payment_phase_yes":
        context.user_data["payment_phases"] = []
        context.user_data["payment_phase_counter"] = 1
        await query.edit_message_text(
            text="Please provide the amount for the 1st Payment:"
        )
        context.user_data["state"] = COLLECTING_PHASE_AMOUNT
    elif data == "payment_phase_add_another":
        counter = context.user_data.get("payment_phase_counter", 1)
        ordinal = to_ordinal(counter)
        context.user_data["state"] = COLLECTING_PHASE_AMOUNT
        await query.edit_message_text(
            text=f"Please provide the amount for the {ordinal} Payment:"
        )
    elif data == "payment_phase_calculate_balance":
        # Use the helper to calculate and add/update 'Final Payment'
        recalculate_final_payment(context.user_data)
        context.user_data["payment_phases_complete"] = True

        # Get the balance for the message
        balance = 0
        for phase in context.user_data.get("payment_phases", []):
            if phase.get("name") == "Final Payment":
                balance = phase.get("amount", 0)
                break

        await query.edit_message_text(
            text=f"✅ Final balance of RM {balance:,.2f} calculated and added."
        )
        await check_and_transition(update, context)
        return
    elif data == "payment_phase_done":
        context.user_data["payment_phases_complete"] = True
        await query.edit_message_text(text="✅ Payment schedule confirmed.")
        await check_and_transition(update, context)
        return
    elif data == "payment_phase_no":
        context.user_data["payment_phases_complete"] = True
        await query.edit_message_text(text="No payment schedule will be added.")
        await check_and_transition(update, context)
    elif data == "payment_phase_start_over":
        context.user_data["payment_phases"] = []
        context.user_data["payment_phase_counter"] = 1
        await query.edit_message_text(
            text="Payment schedule cleared. Please provide the amount for the 1st Payment:"
        )
        context.user_data["state"] = COLLECTING_PHASE_AMOUNT


async def rental_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("rental_period_"):
        period = data.replace("rental_period_", "")
        context.user_data["rental_period_type"] = period
        if period == "daily":
            context.user_data["state"] = WAITING_FOR_RENTAL_START_DATE
            await query.edit_message_text(
                text="Please provide the Rental Start Date (YYYY-MM-DD):"
            )
        else:
            reply_markup = build_contract_period_keyboard()
            await query.edit_message_text(
                text="Please select the contract period:", reply_markup=reply_markup
            )
    elif data.startswith("rental_equip_"):
        if data == "rental_equip_done":
            context.user_data["rental_equipment_collected"] = True
            await query.edit_message_text(text="All rental details collected.")
            await check_and_transition(update, context)
            return
        elif data == "rental_equip_add_other":
            context.user_data["state"] = WAITING_FOR_CUSTOM_EQUIPMENT
            await query.edit_message_text(
                "Please type the name of the equipment you want to add:"
            )
            return

        item_name = data.replace("rental_equip_", "")
        selected_equipment = context.user_data.get("selected_equipment", [])
        if item_name in selected_equipment:
            selected_equipment.remove(item_name)
        else:
            selected_equipment.append(item_name)
        context.user_data["selected_equipment"] = selected_equipment
        reply_markup = build_equipment_keyboard(selected_equipment)
        await query.edit_message_reply_markup(reply_markup=reply_markup)


async def contract_period_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    period = query.data.replace("contract_period_", "")
    if period == "others":
        context.user_data["state"] = AWAITING_INFO
        context.user_data["waiting_for_field"] = "contract_period"
        await query.edit_message_text(text="Please specify the contract period:")
    else:
        context.user_data["contract_period"] = period
        context.user_data["state"] = AWAITING_INFO
        context.user_data["waiting_for_field"] = "rental_amount"
        await query.edit_message_text(
            text=f"Contract period set to {period}. Now, please provide the monthly rental amount:"
        )


async def remove_items_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    """Handles the removal of a line item and ensures data persistence."""
    query = update.callback_query
    await query.answer()

    # Parse callback data: format is "remove_item_{type}_{index}"
    parts = query.data.split("_")

    # Validate callback data format
    if len(parts) < 4:
        await query.edit_message_text("❌ Invalid item selection.")
        return

    try:
        item_index = int(parts[-1])
        item_type = "_".join(parts[2:-1])
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Invalid item format.")
        return

    removed_item_desc = "Unknown Item"

    # Get current items
    main_items = context.user_data.get("line_items", [])
    service_items = context.user_data.get("service_line_items", [])

    try:
        # Handle different item types with bounds checking
        if item_type == "main_item":
            if 0 <= item_index < len(main_items):
                removed_item = main_items.pop(item_index)
                removed_item_desc = removed_item.get("line_description", "Unknown")
                context.user_data["line_items"] = main_items
            else:
                await query.edit_message_text("❌ Item not found (invalid index).")
                return

        elif item_type == "service_item":
            if 0 <= item_index < len(service_items):
                removed_item = service_items.pop(item_index)
                removed_item_desc = removed_item.get("line_description", "Unknown")
                context.user_data["service_line_items"] = service_items
            else:
                await query.edit_message_text("❌ Item not found (invalid index).")
                return

        elif item_type == "main_rental_item":
            if "main_rental_item" in context.user_data:
                removed_item = context.user_data.pop("main_rental_item")
                removed_item_desc = removed_item.get("line_description", "Rental Item")
            else:
                await query.edit_message_text("❌ Rental item not found.")
                return
        else:
            await query.edit_message_text(f"❌ Unknown item type: {item_type}")
            return

        # Show success message
        await query.edit_message_text(text=f"✅ Removed '{removed_item_desc}'.")

        # Send updated confirmation message
        await send_confirmation_message(update, context, is_review=False)

        # Check if there are still items to remove
        from .keyboards import build_remove_items_keyboard

        remaining_items_count = (
            len(context.user_data.get("line_items", []))
            + len(context.user_data.get("service_line_items", []))
            + (1 if context.user_data.get("main_rental_item") else 0)
        )

        if remaining_items_count > 0:
            reply_markup = build_remove_items_keyboard(context.user_data)
            await query.message.reply_text(
                "Select another item to remove, or click 'Done Removing'.",
                reply_markup=reply_markup,
            )
        else:
            # All items removed - return to edit menu automatically
            await query.message.reply_text(
                "✅ All items have been removed. Returning to edit menu."
            )
            context.user_data["state"] = SELECTING_FIELD_TO_EDIT
            from .keyboards import build_edit_fields_keyboard

            reply_markup = build_edit_fields_keyboard(context.user_data)
            await query.message.reply_text(
                "Which field would you like to edit?",
                reply_markup=reply_markup,
            )

    except Exception as e:
        logger.error(f"Error in remove_items_callback_handler: {e}")
        await query.message.reply_text(f"❌ An error occurred: {str(e)}")


async def price_clarification_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data.split("_")
    action = data[1]
    item_index = int(data[2])
    item = context.user_data["line_items"][item_index]
    if action == "total":
        item["unit_price"] = item["unit_price"] / item["qty"]
    await query.edit_message_text(
        f"✅ Understood. Price for '{item['line_description']}' set to RM {item['unit_price']:.2f} per piece."
    )
    await ask_for_price_clarification(update, context)


async def customer_flow_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("select_matched_customer_"):
        matched_name = data.replace("select_matched_customer_", "")
        context.user_data["matched_customer_name"] = matched_name
        data = "use_existing_customer"
    if data == "use_existing_customer":
        matched_name = context.user_data.get("matched_customer_name")
        if not matched_name:
            await query.edit_message_text("An error occurred, please try again.")
            return
        customer_details = await search_customer_by_name(matched_name)
        if customer_details and matched_name in customer_details:
            customer_data = customer_details[matched_name]
            context.user_data.update(
                {
                    "company_name": customer_data.get("name"),
                    "company_address": customer_data.get("address"),
                    "cust_contact": customer_data.get("contact"),
                    "is_new_customer": False,
                }
            )
            await query.edit_message_text(
                f"Existing data for '{matched_name}' loaded. Proceeding..."
            )
        else:
            await query.edit_message_text(
                f"Could not retrieve details for '{matched_name}'. Using current data."
            )
        context.user_data["customer_checked"] = True
        context.user_data["customer_selected"] = True
        await check_and_transition(update, context)
    elif data == "use_extracted_data":
        context.user_data["is_new_customer"] = True
        context.user_data["customer_checked"] = True
        context.user_data["customer_selected"] = True
        await query.edit_message_text(
            "Understood. Using the provided data as a new customer entry."
        )
        await check_and_transition(update, context)


async def confirm_company_name_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data

    # Clean up flags first, before calling check_and_transition
    extracted_name_to_confirm = context.user_data.pop(
        "extracted_image_company_name", None
    )
    context.user_data.pop("is_company_name_from_image_extracted", None)
    # Also pop any extracted address/contact that came with the image if we decide not to use them
    extracted_address = context.user_data.pop(
        "extracted_image_company_address", None
    )  # If we decide to store it separately
    extracted_contact = context.user_data.pop(
        "extracted_image_cust_contact", None
    )  # If we decide to store it separately

    if data == "confirm_company_name_yes":
        # The correct name and address are already in user_data from handle_photo.
        # We just need to confirm and proceed.
        await query.edit_message_text(
            text=f"✅ Confirmed customer name: '{context.user_data.get('company_name', '')}'. Proceeding..."
        )

    elif data == "confirm_company_name_no":
        # Clear the main company_name and address (if they were populated by the image)
        context.user_data.pop("company_name", None)
        context.user_data.pop("company_address", None)
        context.user_data.pop("cust_contact", None)

        await query.edit_message_text(
            text="Okay, please provide the customer's company name:"
        )
        context.user_data["state"] = AWAITING_INFO
        context.user_data["waiting_for_field"] = "company_name"
        return  # Return immediately as check_and_transition will be called in handle_text

    await check_and_transition(update, context)


async def post_generation_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "post_generation_proforma":
        if context.user_data.get("is_proforma"):
            await query.edit_message_text("This is already a Proforma Invoice.")
            return

        context.user_data["is_proforma"] = True
        logger.info("Setting is_proforma to True in user_data")
        # Explicitly remove the old display flag if it exists from previous sessions
        context.user_data.pop("is_proforma_display", None)

        await query.edit_message_text("Converting to Proforma Invoice...")
        await dispatch_request(update, context)

    elif data == "post_generation_edit":
        context.user_data["state"] = SELECTING_FIELD_TO_EDIT
        reply_markup = build_edit_fields_keyboard(context.user_data)
        await query.message.reply_text(
            "Which field would you like to edit?", reply_markup=reply_markup
        )

    elif data == "post_generation_start_new":
        await start_command(update, context)


async def rental_fee_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data

    _, action, fee_name = data.split("_", 2)

    fees_to_ask = context.user_data.get("fees_to_ask", [])
    if fee_name in fees_to_ask:
        fees_to_ask.remove(fee_name)
    context.user_data["fees_to_ask"] = fees_to_ask

    if action == "skip":
        is_monthly = context.user_data.get("rental_period_type") == "monthly"

        # Special "excluded" logic ONLY for these fees on monthly rentals
        if is_monthly and fee_name in ["road_tax", "insurance", "puspakom"]:
            context.user_data[f"{fee_name}_is_excluded"] = True
            context.user_data[f"{fee_name}_amount"] = 0  # Set amount to 0

            # Rebuild and proceed to next fee
            rebuild_rental_fee_items(context)
            await query.edit_message_text(
                text=f"Okay, {fee_name.replace('_', ' ').title()} will be shown as Not Included."
            )
            await ask_for_next_rental_fee(update, context)
            return

        # Default "skip" behavior for all other cases (daily rentals, sticker, agreement, etc.)
        if f"{fee_name}_amount" in context.user_data:
            del context.user_data[f"{fee_name}_amount"]

        if context.user_data.get("rental_fees_collected"):
            rebuild_rental_fee_items(context)
            context.user_data["state"] = SELECTING_FIELD_TO_EDIT
            reply_markup = build_edit_fields_keyboard(context.user_data)
            await query.edit_message_text(
                text=f"Okay, {fee_name.replace('_', ' ').title()} excluded. Returning to menu.",
                reply_markup=reply_markup,
            )
        else:
            await query.edit_message_text(
                text=f"Okay, {fee_name.replace('_', ' ').title()} will be excluded."
            )
            await ask_for_next_rental_fee(update, context)

    elif action == "included":
        context.user_data[f"{fee_name}_amount"] = 0

        # Check if we are editing
        if context.user_data.get("rental_fees_collected"):
            rebuild_rental_fee_items(context)
            context.user_data["state"] = SELECTING_FIELD_TO_EDIT
            reply_markup = build_edit_fields_keyboard(context.user_data)
            await query.edit_message_text(
                text=f"Okay, {fee_name.replace('_', ' ').title()} marked as included. Returning to menu.",
                reply_markup=reply_markup,
            )
        else:
            await query.edit_message_text(
                text=f"Okay, {fee_name.replace('_', ' ').title()} will be marked as included."
            )
            await ask_for_next_rental_fee(update, context)

    elif action == "price":
        context.user_data["state"] = AWAITING_INFO
        context.user_data["waiting_for_field"] = f"{fee_name}_amount"
        await query.edit_message_text(
            text=f"Please provide the price for {fee_name.replace('_', ' ').title()}:"
        )


async def back_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    state_history = context.user_data.get("state_history", [])
    if state_history:
        # Pop the current state
        state_history.pop()
        if state_history:
            # Get the previous state
            previous_state = state_history.pop()
            context.user_data["state"] = previous_state
            # Re-trigger the logic for the previous state
            await check_and_transition(update, context)
            return

    # If no history, just go back to the start
    await start_command(update, context)


async def master_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    # Push current state to history before processing new callback if different from last
    state_history = context.user_data.get("state_history", [])
    current_state = context.user_data.get("state")
    if not state_history or state_history[-1] != current_state:
        state_history.append(current_state)
    context.user_data["state_history"] = state_history

    if data == "back":
        await back_callback_handler(update, context)
        return

    if data == "skip":
        await query.answer()
        field_to_skip = context.user_data.pop("waiting_for_field", None)
        if field_to_skip:
            context.user_data[field_to_skip] = "N/A"
            await query.edit_message_text(
                f"✅ Skipped {field_to_skip.replace('_', ' ')}."
            )
            await check_and_transition(update, context)
            return
        elif context.user_data.get("state") == AWAITING_PAYMENT_PHASE_REMARKS:
            phases = context.user_data.get("payment_phases", [])
            if phases:
                phases[-1]["remarks"] = ""

            await query.edit_message_text("✅ Remarks skipped.")

            context.user_data["payment_phase_counter"] += 1

            # Recalculate to ensure ordering (1st, 2nd... Final)
            recalculate_final_payment(context.user_data)

            # Redirect to the review/edit menu instead of the 'What next' question
            await ask_for_payment_phase_review(update, context)
            return
        else:
            logger.warning(f"Skip pressed in unexpected state: {current_state}")
            await query.edit_message_text("Nothing to skip here.")
            await check_and_transition(update, context)
            return

    if data.startswith("doc_type_"):
        await doc_type_callback_handler(update, context)
    elif data.startswith("review_item_"):
        await line_item_review_callback_handler(update, context)
    elif data.startswith("edit_item_field_"):
        await line_item_field_edit_callback_handler(update, context)
    elif data.startswith("review_"):
        await review_callback_handler(update, context)
    elif data.startswith("edit_payment_phase_") or data.startswith(
        "remove_payment_phase_"
    ):
        await edit_payment_phase_options_callback_handler(update, context)
    elif data.startswith("edit_value_") or data.startswith("remove_field_"):
        await field_edit_options_callback_handler(update, context)
    elif data.startswith("edit_service_price_"):
        service_name = data.replace("edit_service_price_", "")
        context.user_data["editing_service"] = service_name
        context.user_data["state"] = EDITING_SERVICE_PRICE
        await query.edit_message_text(
            text=f"Please provide the new price for '{service_name}':"
        )
    elif data.startswith("remove_service_"):
        service_name = data.replace("remove_service_", "")

        # Remove from selected services
        selected_services = context.user_data.get("selected_services", [])
        if service_name in selected_services:
            selected_services.remove(service_name)
        context.user_data["selected_services"] = selected_services

        # Remove from priced items
        for item_list_name in ["service_line_items", "temp_service_line_items"]:
            item_list = context.user_data.get(item_list_name, [])
            context.user_data[item_list_name] = [
                item for item in item_list if item["line_description"] != service_name
            ]

        await query.edit_message_text(text=f"✅ Service '{service_name}' removed.")
        await ask_for_service_review(update, context)  # Return to review menu
    elif data.startswith("edit_"):
        await edit_selection_callback_handler(update, context)
    elif data.startswith("company_"):
        await button_callback_handler(update, context)
    elif data.startswith("final_confirm_"):
        await final_confirmation_handler(update, context)
    elif data.startswith("add_new_"):
        await add_new_detail_callback_handler(update, context)
    elif data.startswith("lorry_sale_type_"):
        await lorry_sale_type_callback_handler(update, context)
    elif data.startswith("payment_phase_"):
        await payment_phase_callback_handler(update, context)
    elif (
        data.startswith("rental_price_")
        or data.startswith("rental_included_")
        or data.startswith("rental_skip_")
    ):
        await rental_fee_callback_handler(update, context)
    elif data.startswith("rental_period_") or data.startswith("rental_equip_"):
        await rental_callback_handler(update, context)
    elif data.startswith("contract_period_"):
        await contract_period_callback_handler(update, context)
    elif data.startswith("remove_item_"):
        await remove_items_callback_handler(update, context)
    elif data.startswith("clarify_"):
        await price_clarification_callback_handler(update, context)
    elif data.startswith("use_") or data.startswith("select_matched_customer_"):
        await customer_flow_callback_handler(update, context)
    elif data.startswith("confirm_company_name_"):
        await confirm_company_name_callback_handler(update, context)
    elif data.startswith("post_generation_"):
        await post_generation_callback_handler(update, context)
    elif data.startswith("main_service_"):
        await main_service_callback_handler(update, context)
    elif data.startswith("sub_service_"):
        await sub_service_callback_handler(update, context)
    elif data.startswith("additional_"):
        await additional_service_navigation_handler(update, context)
    else:
        # A simple fallback for unhandled callbacks
        logger.warning(f"Unhandled callback query with data: {data}")
        await query.answer("Action not recognized.")


async def doc_type_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    doc_type = query.data.replace("doc_type_", "")
    context.user_data["doc_type"] = doc_type
    await query.edit_message_text(text=f"Selected quote type: {doc_type.capitalize()}.")
    await check_and_transition(update, context)


async def edit_payment_phase_options_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("edit_payment_phase_amount_"):
        phase_index = int(data.replace("edit_payment_phase_amount_", ""))
        context.user_data["editing_payment_phase_index"] = phase_index
        context.user_data["state"] = EDITING_PAYMENT_PHASE_AMOUNT
        await query.edit_message_text(
            text="Please provide the new amount for this payment phase:"
        )
    elif data.startswith("edit_payment_phase_remarks_"):
        phase_index = int(data.replace("edit_payment_phase_remarks_", ""))
        context.user_data["editing_payment_phase_index"] = phase_index
        context.user_data["state"] = EDITING_PAYMENT_PHASE_REMARKS
        await query.edit_message_text(
            text="Please provide the new remarks for this payment phase:"
        )
    elif data.startswith("remove_payment_phase_"):
        phase_index = int(data.replace("remove_payment_phase_", ""))
        phases = context.user_data.get("payment_phases", [])
        if 0 <= phase_index < len(phases):
            removed_phase = phases.pop(phase_index)
            # Recalculate Final Payment after removal
            recalculate_final_payment(context.user_data)
            await query.edit_message_text(
                text=f"✅ '{removed_phase.get('name')}' removed and balance recalculated."
            )
            await ask_for_payment_phase_review(update, context)  # Return to review
        else:
            await query.edit_message_text("Invalid phase selection.")
    elif data.startswith("edit_payment_phase_") and not (
        "_amount_" in data or "_remarks_" in data
    ):
        phase_index = int(data.replace("edit_payment_phase_", ""))
        reply_markup = build_edit_payment_phase_options_keyboard(phase_index)
        await query.edit_message_text(
            "What would you like to edit for this payment phase?",
            reply_markup=reply_markup,
        )
    elif data == "edit_payment_phases":
        # Redirect to review function
        await ask_for_payment_phase_review(update, context)


async def line_item_review_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles callbacks from the line item review keyboard."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("review_item_edit_"):
        item_index = int(data.replace("review_item_edit_", ""))
        context.user_data["editing_line_item_index"] = item_index

        reply_markup = build_line_item_field_edit_keyboard(item_index)
        await query.edit_message_text(
            "Which field do you want to edit?", reply_markup=reply_markup
        )

    elif data.startswith("edit_item_field_"):
        parts = data.replace("edit_item_field_", "").split("_")
        field, item_index = parts[0], int(parts[1])

        context.user_data["editing_line_item_field"] = field
        context.user_data["state"] = REVIEWING_LINE_ITEMS
        await query.edit_message_text(f"Please provide the new {field}:")

    elif data.startswith("review_item_remove_"):
        item_index = int(data.replace("review_item_remove_", ""))
        line_items = context.user_data.get("line_items", [])
        if 0 <= item_index < len(line_items):
            line_items.pop(item_index)
        await query.edit_message_text("✅ Item removed.")
        await ask_for_line_item_review(update, context)

    elif data == "review_item_add":
        context.user_data["state"] = AWAITING_INFO
        context.user_data["waiting_for_field"] = "line_items"
        await query.edit_message_text(
            "Please provide the new line item to append (e.g., 'description - RM price'):"
        )

    elif data == "review_item_done":
        await query.edit_message_text("✅ Line items confirmed.")
        await check_and_transition(update, context)


async def line_item_field_edit_callback_handler(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handles the selection of a line item field to edit."""
    query = update.callback_query
    await query.answer()
    data = query.data

    parts = data.replace("edit_item_field_", "").split("_")
    field, item_index = parts[0], int(parts[1])

    context.user_data["editing_line_item_field"] = field
    context.user_data["editing_line_item_index"] = int(item_index)
    context.user_data["state"] = REVIEWING_LINE_ITEMS
    await query.edit_message_text(f"Please provide the new {field}:")
