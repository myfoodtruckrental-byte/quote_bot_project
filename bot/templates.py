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
    return f"I'm missing the {prompt}. Please provide it."

def edit_field_prompt(field_name):
    return f"Please provide the new value for {field_name.replace('_', ' ')}:"

def build_confirmation_text(data, is_review=False) -> str:
    """Builds the large multi-line confirmation message."""
    if is_review:
        confirmation_text = "I've extracted the following details. Please review them:\n\n"
    else:
        confirmation_text = "Please confirm the final details below:\n\n"
    
    # Common fields
    confirmation_text += f"Lorry No: {get_display_value(data.get('truck_number'))}\n"
    confirmation_text += f"Customer: {get_display_value(data.get('company_name'))}\n"
    confirmation_text += f"Address: {get_display_value(data.get('company_address'))}\n"
    confirmation_text += f"Contact: {get_display_value(data.get('cust_contact'))}\n"
    confirmation_text += f"Salesperson: {get_display_value(data.get('salesperson'))}\n"
    confirmation_text += f"Issuing Company: {get_display_value(data.get('issuing_company'))}\n\n"

    doc_type = data.get("doc_type")
    if doc_type == "rental":
        rental_period = data.get('rental_period_type', 'monthly')
        confirmation_text += "--- Rental Details ---\n"
        confirmation_text += f"Contract Period: {get_display_value(data.get('contract_period'))}\n"

        if rental_period == 'daily':
            confirmation_text += f"Rental Start Date: {get_display_value(data.get('rental_start_date'))}\n"
            confirmation_text += f"Rental End Date: {get_display_value(data.get('rental_end_date'))}\n"
            confirmation_text += f"Number of Days: {get_display_value(data.get('rental_days'))}\n"
            confirmation_text += f"Total Rental Amount: {get_display_value(data.get('rental_amount'), is_price=True)}\n"
        else: # Monthly
            confirmation_text += f"Monthly Rental: {get_display_value(data.get('rental_amount'), is_price=True)}\n"
            confirmation_text += f"Deposit Condition: {get_display_value(data.get('deposit_condition'))}\n"
        
        # These should be shown for both daily and monthly
        confirmation_text += f"Security Deposit: {get_display_value(data.get('security_deposit'), is_price=True)}\n"
        if data.get('deposit_amount'):
            confirmation_text += f"Deposit Amount: {get_display_value(data.get('deposit_amount'), is_price=True)}\n"

        confirmation_text += f"Road Tax (6mo): {get_display_value(data.get('road_tax_amount'), is_price=True)}\n"
        confirmation_text += f"Insurance (6mo): {get_display_value(data.get('insurance_amount'), is_price=True)}\n"
        if data.get('sticker_amount'):
            confirmation_text += f"Sticker Amount: {get_display_value(data.get('sticker_amount'), is_price=True)}\n"
        if data.get('puspakom_amount') is not None:
            confirmation_text += f"PUSPAKOM Fee: {get_display_value(data.get('puspakom_amount'), is_price=True)}\n"
        if data.get('agreement_amount') is not None:
            confirmation_text += f"Agreement Fee: {get_display_value(data.get('agreement_amount'), is_price=True)}\n"
        confirmation_text += "\n"
        
        if data.get('selected_equipment'):
            confirmation_text += "Equipment Provided:\n" + "\n".join([f"- {item}" for item in data['selected_equipment']])

    else: # Sales and Refurbish
        confirmation_text += f"Body: {get_display_value(data.get('body'))}\n\n"
        
        if data.get("line_items"):
            confirmation_text += "Line Items:\n"
            for item in data["line_items"]:
                if isinstance(item, dict):
                    price_display = get_display_value(item.get('unit_price'), is_price=True)
                    line_desc = item.get('line_description', 'N/A')
                else: # Fallback if item is not a dict
                    price_display = "N/A"
                    line_desc = str(item)
                confirmation_text += f"- {line_desc}: {price_display}\n"
        
        if data.get("service_line_items"):
            confirmation_text += "\nAdditional Services:\n"
            for item in data["service_line_items"]:
                if isinstance(item, dict):
                    price_display = get_display_value(item.get('unit_price'), is_price=True)
                    line_desc = item.get('line_description', 'N/A')
                else: # Fallback if item is not a dict
                    price_display = "N/A"
                    line_desc = str(item)
                confirmation_text += f"- {line_desc}: {price_display}\n"
        
        if data.get("payment_phases"):
            confirmation_text += "\nPayment Schedule:\n"
            for phase in data["payment_phases"]:
                amount_display = get_display_value(phase.get('amount'), is_price=True)
                confirmation_text += f"- {phase.get('name', 'N/A')}: {amount_display}\n"
                
    return confirmation_text
