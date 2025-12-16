# services_config.py

SALES_SERVICES = {
    "Registration & Ownership": [
        "Puspakom Inspection",
        "Ownership Transfer",
        "Own Puspakom",
        "Own Tukar Nama",
    ],
    "Road Tax": [
        "Road tax 6month",
        "Road tax 1year",
        "OWN Roadtax"
    ],
    "Insurance": [
        "Insurance 1st party",
        "Insurance 3rd party",
        "Insurance 3rd party fire and theft",
        "OWN Insurance"
    ],
    "Body Work & Modifications": {
        "Body Repairs": None,
        "Spray Painting": [
            "Spray Paint Cabin (Kepala)",
            "Spray Paint Body (Box)",
            "Spray Paint Full Body (Cabin & Box)",
            "Others"
        ],
        "Chassis Extension": [
            "Chasis Extend (10ft to 13ft)",
            "Chasis Extend (14ft to 17ft)",
            "Chasis Extend (14ft to 20ft)",
            "Chasis Extend (17ft to 20ft)",
            "Others"
        ],
        "Change of Body": [
            "Body Tipper",
            "Body Box",
            "Body Foodtruck",
            "Body Ro-ro",
            "Body Kargo",
            "Body Refrigerated Box",
            "Body Container",
            "Body Curtain Sider",
            "Body Water Tank",
            "Others"
        ]
    },
    "Add-Ons": {
        "Aircond": None,
        "Wiring": None,
        "Tyre Botak Tukar": None,
        "Service": None,
        "Others": None
    }
}

GL_CODE_MAPPING = {
    "lorry sale": "500-000",
    "rental": "535-000",
    "refurbish": "501-000",
    "repair": "501-000",
    "service": "501-000",
    "jpj": "930-000",
    "road tax": "930-000",
    "insurance": "931-000",
    "sticker": "501-000", # Default for sticker
    "agreement fee": "501-000" # Default for agreement fee
}
