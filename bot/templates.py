# bot/templates.py

from .helpers import get_display_value


def analyzing_request():
    return "Analyzing your request..."


def extracted_details_review():
    return "I've extracted some details. Please review them."


def details_confirmed():
    return "Details confirmed. Checking for any other missing information..."


def generic_error():
    return "An error occurred, please try again."


def invalid_input(error_message):
    return f"❌ {error_message}\n\nPlease try again:"


def missing_field_prompt(prompt):
    guidance = {
        "truck_number": "e.g., 'VAN 5222'",
        "company_name": "e.g., 'ABC Sdn Bhd'",
        "company_address": "e.g., '123, Jalan ABC, 12345 Kuala Lumpur'",
        "cust_contact": "e.g., '012-3456789'",
        "body": "e.g., 'Wooden Cargo'",
        "salesperson": "e.g., 'John Doe'",
        "rental_start_date": "e.g., '2023-12-31'",
        "rental_end_date": "e.g., '2024-01-30'",
        "contract_period": "e.g., '1 year'",
        "rental_amount": "e.g., '1500'",
        "security_deposit": "e.g., '3000'",
        "road_tax_amount": "e.g., '500'",
        "insurance_amount": "e.g., '2000'",
        "sticker_amount": "e.g., '100'",
        "agreement_amount": "e.g., '250'",
        "puspakom_amount": "e.g., '150'",
    }
    return f"I'm missing the {prompt}. Please provide it, or enter '0' or 'N/A' to skip.\n\nGuidance: {guidance.get(prompt, 'No guidance available.')}"


def edit_field_prompt(field_name):
    return f"Please provide the new value for {field_name.replace('_', ' ')}:"


def build_confirmation_text(data, is_review=False) -> str:
    """Builds the large multi-line confirmation message."""
    if data.get("is_proforma"):
        confirmation_text = "📄 **Proforma Invoice** 📄\n\n"
    elif is_review:
        confirmation_text = (
            "I've extracted the following details. Please review them:\n\n"
        )
    else:
        confirmation_text = "Please confirm the final details below:\n\n"

    # Common fields
    confirmation_text += f"Lorry No: {get_display_value(data.get('truck_number'))}\n"
    confirmation_text += f"Customer: {get_display_value(data.get('company_name'))}\n"
    confirmation_text += f"Address: {get_display_value(data.get('company_address'))}\n"
    confirmation_text += f"Contact: {get_display_value(data.get('cust_contact'))}\n"
    confirmation_text += f"Salesperson: {get_display_value(data.get('salesperson'))}\n"
    confirmation_text += (
        f"Issuing Company: {get_display_value(data.get('issuing_company'))}\n\n"
    )

    doc_type = data.get("doc_type")
    if doc_type == "rental":
        rental_period = data.get("rental_period_type", "monthly")
        confirmation_text += "--- Rental Details ---\n"
        confirmation_text += (
            f"Contract Period: {get_display_value(data.get('contract_period'))}\n"
        )

        if rental_period == "daily":
            confirmation_text += f"Rental Start Date: {get_display_value(data.get('rental_start_date'))}\n"
            confirmation_text += (
                f"Rental End Date: {get_display_value(data.get('rental_end_date'))}\n"
            )
            confirmation_text += (
                f"Number of Days: {get_display_value(data.get('rental_days'))}\n"
            )
            confirmation_text += f"Total Rental Amount: {get_display_value(data.get('rental_amount'), is_price=True)}\n"
        else:  # Monthly
            confirmation_text += f"Monthly Rental: {get_display_value(data.get('rental_amount'), is_price=True)}\n"
            confirmation_text += f"Deposit Condition: {get_display_value(data.get('deposit_condition'))}\n"

        # These should be shown for both daily and monthly
        confirmation_text += f"Security Deposit: {get_display_value(data.get('security_deposit'), is_price=True)}\n"
        if data.get("deposit_amount"):
            confirmation_text += f"Deposit Amount: {get_display_value(data.get('deposit_amount'), is_price=True)}\n"

        confirmation_text += f"Road Tax (6mo): {get_display_value(data.get('road_tax_amount'), is_price=True)}\n"
        confirmation_text += f"Insurance (6mo): {get_display_value(data.get('insurance_amount'), is_price=True)}\n"
        if data.get("sticker_amount"):
            confirmation_text += f"Sticker Amount: {get_display_value(data.get('sticker_amount'), is_price=True)}\n"
        if data.get("puspakom_amount") is not None:
            confirmation_text += f"PUSPAKOM Fee: {get_display_value(data.get('puspakom_amount'), is_price=True)}\n"
        if data.get("agreement_amount") is not None:
            confirmation_text += f"Agreement Fee: {get_display_value(data.get('agreement_amount'), is_price=True)}\n"
        confirmation_text += "\n"

        if data.get("selected_equipment"):
            confirmation_text += "Equipment Provided:\n" + "\n".join(
                [f"- {item}" for item in data["selected_equipment"]]
            )

    else:  # Sales and Refurbish
        confirmation_text += f"Body: {get_display_value(data.get('body'))}\n\n"

        if data.get("line_items"):
            confirmation_text += "Line Items:\n"
            for item in data["line_items"]:
                if isinstance(item, dict):
                    price_display = get_display_value(
                        item.get("unit_price"), is_price=True
                    )
                    qty_display = (
                        f"{item.get('qty', 1)}x " if item.get("qty", 1) > 1 else ""
                    )
                    line_desc = item.get("line_description") or item.get(
                        "description", "N/A"
                    )
                    confirmation_text += (
                        f"- {qty_display}{line_desc}: {price_display}\n"
                    )
                else:  # Fallback if item is not a dict
                    confirmation_text += f"- {str(item)}\n"

        if data.get("service_line_items"):
            confirmation_text += "\n--- Selected Services ---\n"

            # Group services by their main category for better display
            grouped_services = {
                "Tukar Nama": [],
                "Puspakom": [],
                "Road Tax": [],
                "Insurance": [],
                "Body Work & Modifications": {
                    "Body Repairs": [],
                    "Spray Painting": [],
                    "Chassis Extension": [],
                    "Change of Body": [],
                    "Add-Ons": [],
                },
            }

            from services_config import SALES_SERVICES

            for service_item in data["service_line_items"]:
                service_name = service_item.get("line_description")
                price_display = get_display_value(
                    service_item.get("unit_price"), is_price=True
                )

                # Check main categories
                if service_name in SALES_SERVICES.get("Tukar Nama", []):
                    grouped_services["Tukar Nama"].append(
                        f"- {service_name}: {price_display}"
                    )
                elif service_name in SALES_SERVICES.get("Puspakom", []):
                    grouped_services["Puspakom"].append(
                        f"- {service_name}: {price_display}"
                    )
                elif service_name in SALES_SERVICES.get("Road Tax", []):
                    grouped_services["Road Tax"].append(
                        f"- {service_name}: {price_display}"
                    )
                elif service_name in SALES_SERVICES.get("Insurance", []):
                    grouped_services["Insurance"].append(
                        f"- {service_name}: {price_display}"
                    )
                else:  # Check Body Work & Modifications sub-categories
                    found_in_body_work = False
                    for category, sub_list in SALES_SERVICES.get(
                        "Body Work & Modifications", {}
                    ).items():
                        if isinstance(sub_list, list) and service_name in sub_list:
                            grouped_services["Body Work & Modifications"].append(
                                f"- {service_name}: {price_display}"
                            )
                            found_in_body_work = True
                            break
                    if not found_in_body_work:
                        # Fallback for any un-categorized service
                        confirmation_text += (
                            f"- {service_name}: {price_display} (Uncategorized)\n"
                        )

            # Append grouped services to the confirmation text
            for main_cat, items in grouped_services.items():
                if main_cat == "Body Work & Modifications":
                    has_body_work_items = False
                    body_work_text = ""
                    for sub_cat, sub_items in items.items():
                        if sub_items:
                            if not has_body_work_items:
                                body_work_text += f"\n-- {main_cat} --\n"
                                has_body_work_items = True
                            body_work_text += (
                                f"  - {sub_cat}:\n"
                                + "\n".join([f"    {item}" for item in sub_items])
                                + "\n"
                            )
                    if has_body_work_items:
                        confirmation_text += body_work_text
                elif items:
                    confirmation_text += (
                        f"\n-- {main_cat} --\n" + "\n".join(items) + "\n"
                    )

        if data.get("payment_phases"):
            confirmation_text += "\nPayment Schedule:\n"
            for phase in data["payment_phases"]:
                amount_display = get_display_value(phase.get("amount"), is_price=True)
                remarks = phase.get("remarks", "")
                remarks_text = f" ({remarks})" if remarks else ""
                confirmation_text += (
                    f"- {phase.get('name', 'N/A')}: {amount_display}{remarks_text}\n"
                )

    return confirmation_text
