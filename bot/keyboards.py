# bot/keyboards.py
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .constants import EQUIPMENT_LIST

def build_doc_type_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for selecting the document type."""
    keyboard = [
        [InlineKeyboardButton("Sales Quote", callback_data="doc_type_sales")],
        [InlineKeyboardButton("Refurbish Quote", callback_data="doc_type_refurbish")],
        [InlineKeyboardButton("Rental Quote", callback_data="doc_type_rental")],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_review_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for the review step."""
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Continue", callback_data="review_correct")],
        [InlineKeyboardButton("✏️ No, I need to edit", callback_data="review_edit")],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_confirm_generate_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for the final confirmation, offering multiple options."""
    keyboard = [
        [InlineKeyboardButton("✅ Generate PDF", callback_data="final_confirm_generate")],
        [InlineKeyboardButton("✏️ Edit Existing Details", callback_data="final_confirm_edit")],
        [InlineKeyboardButton("➕ Add New Details", callback_data="final_confirm_add_new")],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_edit_fields_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds the dynamic keyboard for selecting a field to edit."""
    keyboard = []
    editable_fields = [
        'truck_number', 'company_name', 'company_address', 'cust_contact',
        'body', 'salesperson', 'rental_start_date', 'rental_end_date', 'rental_amount',
        'security_deposit', 'road_tax_amount', 'insurance_amount', 'sticker_amount'
    ]

    # Special case for sales quote lorry price
    if user_data.get('doc_type') == 'sales' and user_data.get('line_items'):
        keyboard.append([InlineKeyboardButton("✏️ Edit Lorry Price", callback_data="edit_lorry_price")])

    for field in editable_fields:
        if field in user_data:
             keyboard.append([InlineKeyboardButton(f"Edit {field.replace('_', ' ').title()}", callback_data=f"edit_{field}")])

    if user_data.get('doc_type') in ['sales']:
        keyboard.append([InlineKeyboardButton("✏️ Edit Services", callback_data="edit_services")])

    if user_data.get('doc_type') == 'refurbish':
        keyboard.append([InlineKeyboardButton("✏️ Edit Line Items", callback_data="edit_line_items")])
    
    keyboard.append([InlineKeyboardButton("✏️ Edit/Remove Line Items", callback_data="edit_remove_line_items")])
    
    if user_data.get('doc_type') == 'rental':
        keyboard.append([InlineKeyboardButton("✏️ Edit Equipment", callback_data="edit_rental_equipment")])
    
    if 'payment_phases' in user_data:
        keyboard.append([InlineKeyboardButton("✏️ Edit Payment Schedule", callback_data="edit_payment_phases")])
        
    keyboard.append([InlineKeyboardButton("Done Editing", callback_data="edit_done")])
    return InlineKeyboardMarkup(keyboard)

def build_payment_phase_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for adding more payment phases."""
    keyboard = [
        [InlineKeyboardButton("Add Another Payment", callback_data='payment_phase_add_another')],
        [InlineKeyboardButton("Calculate Final Balance", callback_data='payment_phase_calculate_balance')],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_rental_period_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for selecting daily or monthly rental."""
    keyboard = [
        [InlineKeyboardButton("Daily", callback_data='rental_period_daily')],
        [InlineKeyboardButton("Monthly", callback_data='rental_period_monthly')],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_contract_period_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for selecting contract period for monthly rental."""
    keyboard = [
        [InlineKeyboardButton("6 Months", callback_data='contract_period_6 Months')],
        [InlineKeyboardButton("1 Year", callback_data='contract_period_1 Year')],
        [InlineKeyboardButton("2 Years", callback_data='contract_period_2 Years')],
        [InlineKeyboardButton("Others", callback_data='contract_period_others')],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_equipment_keyboard(selected_equipment: list) -> InlineKeyboardMarkup:
    """Builds the keyboard for selecting rental equipment."""
    keyboard = []
    for item in EQUIPMENT_LIST:
        text = f"✅ {item}" if item in selected_equipment else item
        keyboard.append([InlineKeyboardButton(text, callback_data=f"rental_equip_{item}")])
    keyboard.append([InlineKeyboardButton("➡️ Done Selecting Equipment", callback_data="rental_equip_done")])
    return InlineKeyboardMarkup(keyboard)

def build_remove_items_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds a keyboard to select and remove line items."""
    keyboard = []
    
    # Collect all line items with their type and original index
    all_items_to_display = []
    main_items = user_data.get('line_items', [])
    service_items = user_data.get('service_line_items', [])
    rental_main_item = user_data.get('main_rental_item') # For rental quotes

    if main_items:
        for i, item in enumerate(main_items):
            all_items_to_display.append({'type': 'main_item', 'index': i, 'description': item.get('line_description', ''), 'price': item.get('unit_price', 0)})
    
    if service_items:
        for i, item in enumerate(service_items):
            all_items_to_display.append({'type': 'service_item', 'index': i, 'description': item.get('line_description', ''), 'price': item.get('unit_price', 0)})
            
    if rental_main_item: # For rental quotes, main item is separate
        all_items_to_display.append({'type': 'main_rental_item', 'index': 0, 'description': rental_main_item.get('line_description', ''), 'price': rental_main_item.get('unit_price', 0)})

    if not all_items_to_display:
        keyboard.append([InlineKeyboardButton("No items to remove.", callback_data="remove_done")])
        return InlineKeyboardMarkup(keyboard)

    for item_data in all_items_to_display:
        description = item_data['description']
        price = item_data['price']
        item_type = item_data['type']
        item_index = item_data['index']
        
        callback_data = f"remove_item_{item_type}_{item_index}"
        keyboard.append([InlineKeyboardButton(f"🗑️ {description} (RM {price:,.2f})", callback_data=callback_data)])
        
    keyboard.append([InlineKeyboardButton("✅ Done Removing", callback_data="remove_done")])
    return InlineKeyboardMarkup(keyboard)

def build_post_generation_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for after a PDF has been generated."""
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Quote", callback_data="post_generation_edit")],
        [InlineKeyboardButton("🆕 Start New Quote", callback_data="post_generation_start_new")],
    ]
    return InlineKeyboardMarkup(keyboard)

def build_services_keyboard(services_config: dict, category_path: list, selected_services: list) -> InlineKeyboardMarkup:
    """
    Dynamically builds the keyboard for navigating services, using simple callbacks.
    The navigation state is stored in user_data, not in the callback strings.
    """
    keyboard = []
    current_level = services_config
    
    # Traverse the config to the current category level
    for key in category_path:
        current_level = current_level.get(key, {})

    # --- Header ---
    title = " > ".join(category_path) if category_path else "Main Menu"
    keyboard.append([InlineKeyboardButton(f"--- {title} ---", callback_data="ignore")])

    # --- Body (Categories/Services) ---
    if isinstance(current_level, dict):
        for name, sub_level in current_level.items():
            if isinstance(sub_level, (dict, list)): # It's a sub-category
                callback_data = f"category_{name}"
                keyboard.append([InlineKeyboardButton(f"{name} >", callback_data=callback_data)])
            else: # It's a direct service item
                text = f"✅ {name}" if name in selected_services else name
                callback_data = f"service_{name}"
                keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
                
    elif isinstance(current_level, list):
        # It's a leaf node with a list of specific service types
        for service in current_level:
            text = f"✅ {service}" if service in selected_services else service
            callback_data = f"service_{service}"
            keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])

    # --- Footer (Navigation) ---
    if category_path:
        keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="category_back")])

    keyboard.append([InlineKeyboardButton("➡️ Done Selecting ➡️", callback_data="service_done")])
    
    return InlineKeyboardMarkup(keyboard)