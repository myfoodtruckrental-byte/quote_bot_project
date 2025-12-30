# Central configuration for company details

COMPANY_ADDRESSES = {
    "UNIQUE ENTERPRISE": {
        "address": "Lot 4906, Jalan SM6, Taman Sunway Batu Caves,\n68100, Batu Caves, Selangor\nTel: 0166616018 and 0166616019",
        "logo_path": "static/images/UE Logo.webp",
        "ssm_no": "198803042277",
    },
    "CARTRUCKVAN SDN. BHD.": {
        "address": "Lot 4906, Jalan SM6, Taman Sunway Batu Caves,\n68100, Batu Caves, Selangor\nTel: 0166616018 and 0166616019",
        "logo_path": None,
        "ssm_no": "199601008192",
    },
    # "RADI-STAR SDN. BHD.": {
    #     "address": "Lot 4906, Jalan SM6, Taman Sunway Batu Caves,\n68100, Batu Caves, Selangor\nTel: 0166616018 and 0166616019",
    #     "logo_path": None,
    #     "ssm_no": "200201023120",
    # },
}

BANK_DETAILS = {
    "UNIQUE ENTERPRISE": "Public Bank 3203946806",
    "CARTRUCKVAN SDN. BHD.": "ALLIANCE BANK BERHAD : 140640010009752",
    # "RADI-STAR SDN. BHD.": "PUBLIC BANK BERHAD : 3120670022",
}

TERMS_AND_CONDITIONS = {
    "sales": "Quotation valid for 14 days; deposit secures the truck for 2 weeks and becomes non-refundable once work begins or after 14 days. An 80% payment is required to initiate the transfer-of-name process, and full payment is required before release. Ownership of the vehicle and any installed parts remains with {{ issuing_company }} until full settlement. Includes 7 days of free storage, after which RM20/day applies. Customers must provide all required JPJ/APAD documents and are responsible for any delays or losses caused by missing or incomplete documentation. Any deposit or payment made towards this quotation constitutes full acceptance of the quotation and all Terms & Conditions, with or without a signature.",
    "refurbish": "Quotations are valid for 14 days. Booking becomes non-refundable once work starts or after 14 days; 50% upfront payment is required. Workshop may retain the vehicle until all charges are paid (Section 123 CA1950). RM20/day storage applies starting 7 days after completion notice. Customer is responsible for all parking fees, summonses, approvals, and documentation; workshop is not liable for pre-existing damage, hidden defects, lost items, or income loss during repairs. Any deposit or payment made towards this quotation constitutes full acceptance of the quotation and all Terms & Conditions, with or without a signature.",
    "rental": "Booking fees become non-refundable once preparation begins or after 14 days. A booking reserves the truck for 7 days, after which a 50% progress payment is required to continue. After the customer is notified that the truck is ready, 7 days of free storage is provided; thereafter RM20/day applies. If the truck is not collected within 14 days from the ready date, it may be released to other customers. Customers are responsible for providing all required JPJ/APAD documents, approvals, and information — including ensuring that the appointed driver holds a valid GDL (Goods Driving Licence) — and for any delays, rejections, penalties, or losses arising from missing, invalid, or incomplete documentation. Any deposit or payment made towards this quotation constitutes full acceptance of the quotation and all Terms & Conditions, with or without a signature.",
}

REQUIRED_DOCUMENTS = {
    "sales": ["SSM (1 Set)", "Directors IC (1 Set)", "Bank Statements 3-6mth (Loan)"],
    "rental": [
        "SSM (1 set)",
        "Director's IC Copy",
        "Partner's IC Copy",
        "Utility Bill",
        "House / Office Picture",
    ],
    "refurbish": ["Copy of Customer's IC (Both Sides)"],
}
