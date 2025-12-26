import os
import sys
import json

# Add current directory to path to import local modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import pdf_generator


def test_pdf_generation():
    print("Starting PDF Generation Test...")

    # Mock data with N/A values and is_proforma flag
    mock_data = {
        "type": "refurbish",
        "cust_code": "300-C0002",
        "cust_name": "N/A",
        "company_address": "N/A",
        "cust_contact": "N/A",
        "truck_number": "VAN 5222",
        "issuing_company": "UNIQUE ENTERPRISE",
        "doc_no": "TEST-PROFORMA-001",
        "description": "Test Proforma Invoice",
        "salesperson": "N/A",
        "line_items": [
            {
                "qty": 1,
                "line_description": "Repair Box",
                "unit_price": 1000.0,
                "gl_code": "500-000",
            },
            {
                "qty": 2,
                "line_description": "Change plywood",
                "unit_price": 300.0,
                "gl_code": "500-000",
            },
        ],
        "service_line_items": [],
        "payment_phases": [],
        "total_amount": 1600.0,
        "is_proforma": True,
        "body": "N/A",
    }

    print(f"Generating Proforma PDF for: {mock_data['doc_no']}")
    file_path = pdf_generator.generate_pdf_from_data(mock_data)

    if file_path and os.path.exists(file_path):
        print(f"✅ Success! Proforma PDF generated at: {file_path}")
    else:
        print("❌ Failed to generate Proforma PDF.")

    # Test standard quotation
    mock_data["is_proforma"] = False
    mock_data["doc_no"] = "TEST-QUOTE-001"
    print(f"Generating Quotation PDF for: {mock_data['doc_no']}")
    file_path = pdf_generator.generate_pdf_from_data(mock_data)

    if file_path and os.path.exists(file_path):
        print(f"✅ Success! Quotation PDF generated at: {file_path}")
    else:
        print("❌ Failed to generate Quotation PDF.")


if __name__ == "__main__":
    test_pdf_generation()
