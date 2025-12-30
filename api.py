import logging
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import pdf_generator
import os
import sys
import json


# --- Pydantic Models ---
class LineItem(BaseModel):
    qty: int
    line_description: str
    unit_price: float
    gl_code: str


class ServiceLineItem(BaseModel):
    qty: int
    line_description: str
    unit_price: float
    gl_code: str


class QuotationLineItem(BaseModel):
    qty: int
    line_description: str
    unit_price: float
    gl_code: str


class PaymentPhase(BaseModel):
    name: str
    amount: float
    remarks: Optional[str] = None


class MultiLineQuotationData(BaseModel):
    type: str
    cust_code: str
    cust_name: str
    company_address: Optional[str] = None
    cust_contact: Optional[str] = None
    truck_number: str
    body: Optional[str] = None
    issuing_company: str
    doc_no: str
    description: str
    salesperson: Optional[str] = None
    line_items: List[LineItem] = []
    service_line_items: List[LineItem] = []
    excluded_line_items: List[LineItem] = []
    included_services: List[str] = []
    payment_phases: List[PaymentPhase] = []
    total_amount: float
    is_proforma: bool = False

    # Rental specific fields
    main_rental_item: Optional[LineItem] = None
    rental_period_type: Optional[str] = None
    contract_period: Optional[str] = None
    rental_start_date: Optional[str] = None
    rental_end_date: Optional[str] = None
    rental_amount: Optional[float] = None
    deposit_condition: Optional[str] = None
    deposit_amount: Optional[float] = None
    security_deposit: Optional[float] = None
    upfront_rental: Optional[float] = None
    road_tax_amount: Optional[float] = None
    insurance_amount: Optional[float] = None
    sticker_amount: Optional[float] = None
    agreement_fee: Optional[float] = None
    selected_equipment: Optional[List[str]] = None


# --- FastAPI App ---
app = FastAPI()

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Catches Pydantic validation errors and logs them."""
    logger.error(f"Caught validation error: {exc.errors()}")
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.post("/generate_quotation_pdf/")
async def generate_quotation_pdf(quote_data: MultiLineQuotationData):
    """
    Receives quotation data, generates a PDF, and returns the file path.
    """
    try:
        logger.info(f"Received data for PDF generation: {quote_data.doc_no}")
        data_dict = quote_data.model_dump()
        file_path = pdf_generator.generate_pdf_from_data(data_dict)
        if file_path:
            logger.info(f"Successfully generated PDF: {file_path}")
            return {"success": True, "file_path": file_path}
        else:
            logger.error("PDF generation failed, function returned None.")
            raise HTTPException(status_code=500, detail="PDF generation failed.")
    except Exception as e:
        logger.exception("An error occurred during PDF generation.")
        raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")
