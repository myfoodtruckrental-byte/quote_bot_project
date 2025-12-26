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
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_confirm_generate_keyboard(user_data) -> InlineKeyboardMarkup:
    """Builds the keyboard for the final confirmation, offering multiple options."""
    is_proforma_display = user_data.get("is_proforma_display", False)
    proforma_button_text = (
        "Switch to Quotation" if is_proforma_display else "Switch to Proforma Invoice"
    )
    doc_type = user_data.get("doc_type")

    keyboard = [
        [
            InlineKeyboardButton(
                "✅ Generate PDF", callback_data="final_confirm_generate"
            )
        ],
        [
            InlineKeyboardButton(
                proforma_button_text, callback_data="final_confirm_proforma"
            )
        ],
        [
            InlineKeyboardButton(
                "✏️ Edit Existing Details", callback_data="final_confirm_edit"
            )
        ],
    ]

    # Only show "Add New Details" for non-rental and non-sales quotes
    if doc_type not in ["rental", "sales"]:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "➕ Add New Details", callback_data="final_confirm_add_new"
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)


def build_edit_fields_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds the dynamic keyboard for selecting a field to edit."""
    keyboard = []
    editable_fields = [
        "truck_number",
        "company_name",
        "company_address",
        "cust_contact",
        "body",
        "salesperson",
        "rental_start_date",
        "rental_end_date",
        "contract_period",
        "rental_amount",
        "security_deposit",
        "road_tax_amount",
        "insurance_amount",
        "sticker_amount",
        "agreement_amount",
        "puspakom_amount",
        "issuing_company",
    ]

    # Special case for sales quote lorry price
    if user_data.get("doc_type") == "sales" and user_data.get("line_items"):
        keyboard.append(
            [
                InlineKeyboardButton(
                    "✏️ Edit Lorry Price", callback_data="edit_lorry_price"
                )
            ]
        )

    # Force rental fees to be editable for rental quotes, even if missing/skipped
    if user_data.get("doc_type") == "rental":
        rental_fees = [
            "road_tax_amount",
            "insurance_amount",
            "sticker_amount",
            "agreement_amount",
            "puspakom_amount",
        ]
        for fee in rental_fees:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"✏️ Edit {fee.replace('_', ' ').title()}",
                        callback_data=f"edit_{fee}",
                    )
                ]
            )

        # Remove these from editable_fields to avoid duplicates if they exist in user_data
        editable_fields = [f for f in editable_fields if f not in rental_fees]

    for field in editable_fields:
        if field in user_data:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        f"✏️ Edit {field.replace('_', ' ').title()}",
                        callback_data=f"edit_{field}",
                    )
                ]
            )

    if user_data.get("doc_type") in ["sales"]:
        keyboard.append(
            [InlineKeyboardButton("✏️ Edit Services", callback_data="edit_services")]
        )

    if user_data.get("doc_type") == "refurbish":
        keyboard.append(
            [InlineKeyboardButton("✏️ Edit Line Items", callback_data="edit_line_items")]
        )

    if user_data.get("doc_type") == "rental":
        keyboard.append(
            [
                InlineKeyboardButton(
                    "✏️ Edit Equipment", callback_data="edit_rental_equipment"
                )
            ]
        )

    if "payment_phases" in user_data and user_data["payment_phases"]:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "✏️ Edit Payment Schedule", callback_data="edit_payment_phases"
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("Done Editing", callback_data="edit_done")])
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)


def build_payment_phase_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for adding more payment phases."""
    keyboard = [
        [
            InlineKeyboardButton(
                "Add Another Payment", callback_data="payment_phase_add_another"
            )
        ],
        [
            InlineKeyboardButton(
                "Calculate Final Balance",
                callback_data="payment_phase_calculate_balance",
            )
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_rental_period_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for selecting daily or monthly rental."""
    keyboard = [
        [InlineKeyboardButton("Daily", callback_data="rental_period_daily")],
        [InlineKeyboardButton("Monthly", callback_data="rental_period_monthly")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_contract_period_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for selecting contract period for monthly rental."""
    keyboard = [
        [InlineKeyboardButton("6 Months", callback_data="contract_period_6 Months")],
        [InlineKeyboardButton("1 Year", callback_data="contract_period_1 Year")],
        [InlineKeyboardButton("2 Years", callback_data="contract_period_2 Years")],
        [InlineKeyboardButton("Others", callback_data="contract_period_others")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_equipment_keyboard(selected_equipment: list) -> InlineKeyboardMarkup:
    """Builds the keyboard for selecting rental equipment."""
    keyboard = []
    for item in EQUIPMENT_LIST:
        text = f"✅ {item}" if item in selected_equipment else item
        keyboard.append(
            [InlineKeyboardButton(text, callback_data=f"rental_equip_{item}")]
        )
    keyboard.append(
        [
            InlineKeyboardButton(
                "➕ Add Other Equipment", callback_data="rental_equip_add_other"
            )
        ]
    )
    keyboard.append(
        [
            InlineKeyboardButton(
                "➡️ Done Selecting Equipment", callback_data="rental_equip_done"
            )
        ]
    )
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)


def build_post_generation_keyboard() -> InlineKeyboardMarkup:
    """Builds the keyboard for after a PDF has been generated."""
    keyboard = [
        [InlineKeyboardButton("✏️ Edit Quote", callback_data="post_generation_edit")],
        [
            InlineKeyboardButton(
                "🆕 Start New Quote", callback_data="post_generation_start_new"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_main_services_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds the main services menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton(
                "Change of Ownership", callback_data="main_service_tukar_nama"
            )
        ],
        [
            InlineKeyboardButton(
                "Puspakom Inspection", callback_data="main_service_puspakom"
            )
        ],
        [InlineKeyboardButton("Road Tax", callback_data="main_service_road_tax")],
        [InlineKeyboardButton("Insurance", callback_data="main_service_insurance")],
        [
            InlineKeyboardButton(
                "Additional Services", callback_data="main_service_additional"
            )
        ],
        [InlineKeyboardButton("Done with Services", callback_data="main_service_done")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_tukar_nama_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds the keyboard for 'Tukar Nama' options."""
    keyboard = [
        [
            InlineKeyboardButton(
                "Transfer Ownership", callback_data="sub_service_Tukar Nama"
            )
        ],
        [
            InlineKeyboardButton(
                "OWN Transfer Ownership", callback_data="sub_service_OWN Tukar Nama"
            )
        ],
        [
            InlineKeyboardButton(
                "Back to Main Services", callback_data="main_service_back"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_puspakom_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds the keyboard for 'Puspakom' options."""
    keyboard = [
        [
            InlineKeyboardButton(
                "Puspakom Inspection", callback_data="sub_service_Inspection Puspakom"
            )
        ],
        [
            InlineKeyboardButton(
                "OWN Puspakom Inspection",
                callback_data="sub_service_OWN Inspection Puspakom",
            )
        ],
        [
            InlineKeyboardButton(
                "Back to Main Services", callback_data="main_service_back"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_road_tax_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds the keyboard for 'Road Tax' options."""
    keyboard = [
        [
            InlineKeyboardButton(
                "Road Tax (6-Month)", callback_data="sub_service_Road Tax (6Month)"
            )
        ],
        [
            InlineKeyboardButton(
                "OWN Road Tax", callback_data="sub_service_OWN Road Tax"
            )
        ],
        [
            InlineKeyboardButton(
                "Back to Main Services", callback_data="main_service_back"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_insurance_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds the keyboard for 'Insurance' options."""
    keyboard = [
        [InlineKeyboardButton("1st Party", callback_data="sub_service_1st Party")],
        [InlineKeyboardButton("3rd Party", callback_data="sub_service_3rd Party")],
        [
            InlineKeyboardButton(
                "3rd Party (Fire & Theft)",
                callback_data="sub_service_3rd Party fire and Theft",
            )
        ],
        [
            InlineKeyboardButton(
                "OWN Insurance", callback_data="sub_service_OWN Insurance"
            )
        ],
        [
            InlineKeyboardButton(
                "Back to Main Services", callback_data="main_service_back"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_additional_services_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds a keyboard for the main categories of additional services."""
    from services_config import ADDITIONAL_SERVICES

    keyboard = []
    for category in ADDITIONAL_SERVICES.keys():
        keyboard.append(
            [
                InlineKeyboardButton(
                    category.title(), callback_data=f"additional_category_{category}"
                )
            ]
        )

    keyboard.append(
        [
            InlineKeyboardButton(
                "Done with Additional Services", callback_data="additional_done"
            )
        ]
    )

    keyboard.append(
        [
            InlineKeyboardButton(
                "Back to Main Services", callback_data="main_service_back"
            )
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def build_additional_services_subcategory_keyboard(
    category: str, user_data: dict
) -> InlineKeyboardMarkup:
    """Builds a keyboard for sub-categories (Level 2)."""
    from services_config import ADDITIONAL_SERVICES

    keyboard = []
    content = ADDITIONAL_SERVICES.get(category, {})

    # Get currently selected service descriptions
    selected_services = [
        item["line_description"] for item in user_data.get("service_line_items", [])
    ]

    if isinstance(content, dict):
        for sub_cat, items in content.items():
            # Check if any item in this sub-category is selected
            # items is a list of strings
            is_selected = any(item in selected_services for item in items)
            text = f"✅ {sub_cat}" if is_selected else sub_cat

            keyboard.append(
                [InlineKeyboardButton(text, callback_data=f"additional_sub_{sub_cat}")]
            )

    keyboard.append(
        [
            InlineKeyboardButton(
                "Back to Categories", callback_data="additional_category_back"
            )
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def build_additional_services_items_keyboard(
    category: str, sub_category_name: str, user_data: dict
) -> InlineKeyboardMarkup:
    """Builds a keyboard for specific service items (Level 3)."""
    from services_config import ADDITIONAL_SERVICES

    keyboard = []

    # Handle both Dict (nested) and List (direct) structures
    category_content = ADDITIONAL_SERVICES.get(category, {})
    if isinstance(category_content, list):
        # Direct list (Level 1 -> Level 3)
        service_items = category_content
        back_callback = "additional_category_back"
    else:
        # Nested dict (Level 2 -> Level 3)
        service_items = category_content.get(sub_category_name, [])
        back_callback = f"additional_category_{category}"  # Go back to sub-cat list

    currently_added_services = [
        item["line_description"] for item in user_data.get("service_line_items", [])
    ]

    for item in service_items:
        text = f"✅ {item}" if item in currently_added_services else item
        keyboard.append(
            [InlineKeyboardButton(text, callback_data=f"additional_item_{item}")]
        )

    # Add an "Other" option
    # Use sub_category_name if available, else category name
    label = sub_category_name if sub_category_name else category
    keyboard.append(
        [
            InlineKeyboardButton(
                f"➕ Add Other {label}",
                callback_data=f"additional_other_{label}",
            )
        ]
    )

    keyboard.append([InlineKeyboardButton("Back", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)


def build_remove_items_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds a keyboard to select and remove line items."""
    keyboard = []

    # Collect all line items with their type and original index
    all_items_to_display = []
    main_items = user_data.get("line_items", [])
    service_items = user_data.get("service_line_items", [])
    rental_main_item = user_data.get("main_rental_item")  # For rental quotes

    if main_items:
        for i, item in enumerate(main_items):
            if isinstance(item, dict):
                all_items_to_display.append(
                    {
                        "type": "main_item",
                        "index": i,
                        "description": item.get("line_description", ""),
                        "price": item.get("unit_price", 0),
                    }
                )

    if service_items:
        for i, item in enumerate(service_items):
            if isinstance(item, dict):
                all_items_to_display.append(
                    {
                        "type": "service_item",
                        "index": i,
                        "description": item.get("line_description", ""),
                        "price": item.get("unit_price", 0),
                    }
                )

    if rental_main_item and isinstance(
        rental_main_item, dict
    ):  # For rental quotes, main item is separate
        all_items_to_display.append(
            {
                "type": "main_rental_item",
                "index": 0,
                "description": rental_main_item.get("line_description", ""),
                "price": rental_main_item.get("unit_price", 0),
            }
        )

    if not all_items_to_display:
        keyboard.append(
            [InlineKeyboardButton("No items to remove.", callback_data="remove_done")]
        )
        return InlineKeyboardMarkup(keyboard)

    for item_data in all_items_to_display:
        description = item_data["description"]
        price = item_data["price"]
        item_type = item_data["type"]
        item_index = item_data["index"]

        callback_data = f"remove_item_{item_type}_{item_index}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"🗑️ {description} (RM {price:,.2f})", callback_data=callback_data
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("✅ Done Removing", callback_data="remove_done")]
    )
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)


def build_field_edit_options_keyboard(field: str) -> InlineKeyboardMarkup:
    """Builds a keyboard with options to edit, remove, or go back for a specific field."""
    keyboard = [
        [
            InlineKeyboardButton("✏️ Edit Value", callback_data=f"edit_value_{field}"),
            InlineKeyboardButton(
                "🗑️ Remove Field", callback_data=f"remove_field_{field}"
            ),
        ],
        [InlineKeyboardButton("⬅️ Back to Edit Menu", callback_data="edit_done")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_skip_keyboard() -> InlineKeyboardMarkup:
    """Builds a simple keyboard with a single 'Skip' button."""
    keyboard = [[InlineKeyboardButton("Skip", callback_data="skip")]]
    return InlineKeyboardMarkup(keyboard)


def build_edit_payment_schedule_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds the keyboard for editing the payment schedule (Deprecated/Renamed to build_payment_phase_review_keyboard)."""
    # Keeping for compatibility if needed, but logic should use the new one.
    return build_payment_phase_review_keyboard(user_data)


def build_payment_phase_review_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    """Builds a keyboard to review and edit payment phases."""
    keyboard = []
    payment_phases = user_data.get("payment_phases", [])

    for i, phase in enumerate(payment_phases):
        phase_name = phase.get("name", f"Phase {i+1}")
        amount = phase.get("amount", 0)
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"{phase_name}: RM {amount:,.2f}", callback_data="ignore"
                )
            ]
        )
        # Action buttons - Skip for Final Payment
        if phase_name != "Final Payment":
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "✏️ Edit", callback_data=f"edit_payment_phase_{i}"
                    ),
                    InlineKeyboardButton(
                        "🗑️ Remove", callback_data=f"remove_payment_phase_{i}"
                    ),
                ]
            )

    keyboard.append(
        [
            InlineKeyboardButton(
                "➕ Add Payment Phase", callback_data="payment_phase_add_another"
            )
        ]
    )

    # Only show 'Calculate Final Balance' if it hasn't been added yet
    has_final = any(p.get("name") == "Final Payment" for p in payment_phases)
    if not has_final:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🏁 Calculate Final Balance",
                    callback_data="payment_phase_calculate_balance",
                )
            ]
        )

    keyboard.append([InlineKeyboardButton("Done Editing", callback_data="edit_done")])
    return InlineKeyboardMarkup(keyboard)


def build_edit_payment_phase_options_keyboard(phase_index: int) -> InlineKeyboardMarkup:
    """Builds the keyboard for editing a specific payment phase."""
    keyboard = [
        [
            InlineKeyboardButton(
                "Edit Amount", callback_data=f"edit_payment_phase_amount_{phase_index}"
            )
        ],
        [
            InlineKeyboardButton(
                "Edit Remarks",
                callback_data=f"edit_payment_phase_remarks_{phase_index}",
            )
        ],
        [InlineKeyboardButton("⬅️ Back", callback_data="edit_payment_phases")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_line_item_review_keyboard(line_items: list) -> InlineKeyboardMarkup:
    """Builds a keyboard to review and edit extracted line items."""
    keyboard = []
    for i, item in enumerate(line_items):
        desc = item.get("line_description") or item.get("description") or "N/A"
        qty = item.get("qty", "N/A")
        price = item.get("unit_price", "N/A")

        # Main item info row - not a button
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"Item {i+1}: {qty}x {desc} @ RM{price}", callback_data="ignore"
                )
            ]
        )

        # Action buttons for the item
        button_row = [
            InlineKeyboardButton("✏️ Edit", callback_data=f"review_item_edit_{i}"),
            InlineKeyboardButton("🗑️ Remove", callback_data=f"review_item_remove_{i}"),
        ]
        keyboard.append(button_row)

    # Global action buttons
    keyboard.append(
        [
            InlineKeyboardButton("➕ Add Item", callback_data="review_item_add"),
            InlineKeyboardButton("✅ Done", callback_data="review_item_done"),
        ]
    )

    return InlineKeyboardMarkup(keyboard)


def build_line_item_field_edit_keyboard(item_index: int) -> InlineKeyboardMarkup:
    """Builds a keyboard to select which field of a line item to edit."""
    keyboard = [
        [
            InlineKeyboardButton(
                "Description", callback_data=f"edit_item_field_description_{item_index}"
            )
        ],
        [
            InlineKeyboardButton(
                "Quantity", callback_data=f"edit_item_field_qty_{item_index}"
            )
        ],
        [
            InlineKeyboardButton(
                "Price", callback_data=f"edit_item_field_unit_price_{item_index}"
            )
        ],
        [
            InlineKeyboardButton(
                "⬅️ Back to Line Items", callback_data="review_item_back"
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_service_review_keyboard(service_line_items: list) -> InlineKeyboardMarkup:
    """Builds a keyboard to review and edit selected services."""
    keyboard = []
    for i, item in enumerate(service_line_items):
        desc = item.get("line_description") or item.get("description") or "N/A"
        price = item.get("unit_price", "N/A")

        # Main item info row
        keyboard.append(
            [InlineKeyboardButton(f"{desc}: RM {price}", callback_data="ignore")]
        )

        # Action buttons
        button_row = [
            InlineKeyboardButton(
                "✏️ Edit Value", callback_data=f"edit_service_price_{desc}"
            ),
            InlineKeyboardButton("🗑️ Remove", callback_data=f"remove_service_{desc}"),
        ]
        keyboard.append(button_row)

    keyboard.append(
        [
            InlineKeyboardButton("➕ Add Service", callback_data="add_new_service"),
            InlineKeyboardButton("✅ Done", callback_data="edit_done"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)
