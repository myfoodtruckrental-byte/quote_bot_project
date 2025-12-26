# services_config.py

SALES_SERVICES = {
    "Tukar Nama": ["Tukar Nama", "OWN Tukar Nama"],
    "Puspakom": ["Inspection Puspakom", "OWN Inspection Puspakom"],
    "Road Tax": ["Road Tax (6Month)", "OWN Road Tax"],
    "Insurance": [
        "1st Party",
        "3rd Party",
        "3rd Party fire and Theft",
        "OWN Insurance",
    ],
}

ADDITIONAL_SERVICES = {
    "Body Work & Modifications": {
        "Body Repairs": ["Body Repairs"],
        "Spray Painting": [
            "Spray Paint Cabin (Kepala)",
            "Spray Paint Body (Box)",
            "Spray Paint Full Body (Cabin & Box)",
        ],
        "Chassis Extension": [
            "Chassis Extend (10ft to 13ft)",
            "Chassis Extend (14ft to 17ft)",
            "Chassis Extend (14ft to 20ft)",
            "Chassis Extend (17ft to 20ft)",
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
        ],
    },
    "Add-Ons": {
        "Aircond": ["Aircond"],
        "Wiring": ["Wiring"],
        "Tyre Botak Tukar": ["Tyre Botak Tukar"],
        "Service": ["Service"],
    },
    "Other Services": ["Other Services"],
}


GL_CODE_MAPPING = {
    "lorry sale": "500-000",
    "rental": "535-000",
    "refurbish": "501-000",
    "repair": "501-000",
    "service": "501-000",
    "jpj": "930-000",
    "road tax": "930-000",
    "road tax (6month)": "930-000",  # Specific mapping
    "own road tax": "930-000",  # Specific mapping
    "insurance": "931-000",
    "1st party": "931-000",  # Specific mapping
    "3rd party": "931-000",  # Specific mapping
    "3rd party fire and theft": "931-000",  # Specific mapping
    "own insurance": "931-000",  # Specific mapping
    "sticker": "501-000",  # Default for sticker
    "agreement fee": "501-000",  # Default for agreement fee
    "tukar nama": "930-000",  # Specific mapping
    "own tukar nama": "930-000",  # Specific mapping
    "inspection puspakom": "930-000",  # Specific mapping
    "own inspection puspakom": "930-000",  # Specific mapping
    "body repairs": "501-000",
    "spray paint cabin (kepala)": "501-000",
    "spray paint body (box)": "501-000",
    "spray paint full body (cabin & box)": "501-000",
    "custom spray paint": "501-000",
    "chassis extend (10ft to 13ft)": "501-000",
    "chassis extend (14ft to 17ft)": "501-000",
    "chassis extend (14ft to 20ft)": "501-000",
    "chassis extend (17ft to 20ft)": "501-000",
    "custom chassis extension": "501-000",
    "body tipper": "501-000",
    "body box": "501-000",
    "body foodtruck": "501-000",
    "body ro-ro": "501-000",
    "body kargo": "501-000",
    "body refrigerated box": "501-000",
    "body container": "501-000",
    "body curtain sider": "501-000",
    "body water tank": "501-000",
    "custom body change": "501-000",
    "aircond": "501-000",
    "wiring": "501-000",
    "tyre botak tukar": "501-000",
    "custom add-on": "501-000",
    "other services": "501-000",
}
