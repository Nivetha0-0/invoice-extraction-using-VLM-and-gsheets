import os
import json
import fitz
import base64
from PIL import Image
from io import BytesIO
from groq import Groq
import streamlit as st
import gspread

# CONFIG

st.set_page_config(
    page_title="Invoice OCR & Structured Extraction",
    page_icon="📄",
    layout="wide"
)

# Load API Key from Streamlit Secrets
groq_api_key = st.secrets["GROQ_API_KEY"]
client = Groq(api_key=groq_api_key)

# OCR + LLM FUNCTIONS

def pdf_to_images(file, dpi=200):
    file.seek(0)
    doc = fitz.open(stream=file.read(), filetype="pdf")
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        images.append(img)
    return images


def image_to_base64(image):
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def extract_text_with_vision(image):
    base64_image = image_to_base64(image)

    vision_prompt = """
Extract all readable text from this document.
Preserve layout and line breaks.
Do NOT summarize.
Return only raw extracted text.
"""

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                {"type": "text", "text": vision_prompt}
            ],
        }],
        temperature=0
    )

    return response.choices[0].message.content.strip()


def extract_invoice_fields(text):
    prompt = f"""
Extract structured invoice data from the text below.
Do NOT explain.
Return EXACT JSON only.

Schema:

{{
"Vendor":{{"BusinessName":null,"Address":null,"GSTIN":null,"Phone":null,"Email":null}},
"Buyer":{{"Name":null,"BillingAddress":null,"ShippingAddress":null,"GSTIN":null,"Phone":null,"Email":null}},
"Totals":{{"GrandTotal":null}},
"PaymentDetails":{{"ModeOfPayment":null,"BankName":null,"AccountNumber":null,"IFSCCode":null}}
}}

TEXT:
{text}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return response.choices[0].message.content.strip()


def process_document(uploaded_file):
    filename = uploaded_file.name.lower()
    uploaded_file.seek(0)

    full_text = ""

    if filename.endswith(".pdf"):
        images = pdf_to_images(uploaded_file)
        for img in images:
            full_text += extract_text_with_vision(img) + "\n"
    else:
        image = Image.open(uploaded_file).convert("RGB")
        full_text = extract_text_with_vision(image)

    try:
        structured_data = json.loads(extract_invoice_fields(full_text))
        return structured_data
    except:
        st.error("Invalid JSON returned from LLM")
        return None

# GOOGLE SHEETS 

def get_gsheet(sheet_name):
    try:
        credentials_dict = st.secrets["gcp_service_account"]
        gc = gspread.service_account_from_dict(credentials_dict)
        sh = gc.open(sheet_name)
        return sh.sheet1
    except Exception as e:
        st.error(f"Google Sheets error: {e}")
        return None


def get_service_account_email():
    return st.secrets["gcp_service_account"]["client_email"]


def save_invoice_to_sheet(sheet, data):

    vendor = data.get("Vendor", {})
    buyer = data.get("Buyer", {})
    totals = data.get("Totals", {})
    payment = data.get("PaymentDetails", {})

    # ONLY the 16 requested fields
    row = [
        vendor.get("BusinessName"),
        vendor.get("Address"),
        vendor.get("GSTIN"),
        vendor.get("Phone"),
        vendor.get("Email"),
        buyer.get("Name"),
        buyer.get("BillingAddress"),
        buyer.get("ShippingAddress"),
        buyer.get("GSTIN"),
        buyer.get("Phone"),
        buyer.get("Email"),
        totals.get("GrandTotal"),
        payment.get("ModeOfPayment"),
        payment.get("BankName"),
        payment.get("AccountNumber"),
        payment.get("IFSCCode"),
    ]

    try:
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"Error saving to sheet: {e}")
        return False

# UI

st.title("📄 Invoice OCR & Structured Data Extraction")

uploaded_file = st.file_uploader(
    "Upload PDF or Image",
    type=["pdf", "png", "jpg", "jpeg"]
)

if uploaded_file:

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Preview")
        if uploaded_file.name.lower().endswith(".pdf"):
            try:
                pages = pdf_to_images(uploaded_file)
                if pages:
                    st.image(pages[0], use_column_width=True)
            except:
                st.info("Preview unavailable")
        else:
            st.image(uploaded_file, use_column_width=True)

    with col2:
        st.subheader("File Details")
        st.write("Name:", uploaded_file.name)
        st.write("Size:", f"{len(uploaded_file.getvalue())/1024:.1f} KB")
        parse_btn = st.button("🚀 Extract & Parse")

    if parse_btn:
        with st.spinner("Processing document..."):
            result = process_document(uploaded_file)

        if result:
            st.subheader("Extracted Invoice Data")
            st.json(result)

            sheet_name = st.text_input("Google Sheet Name", value="invoice-corrected")

            st.info(f"Share the sheet with: {get_service_account_email()} (Editor)")

            if st.button("💾 Save to Google Sheets"):
                sheet = get_gsheet(sheet_name)
                if sheet and save_invoice_to_sheet(sheet, result):
                    st.success("✅ Invoice saved successfully!")
                else:
                    st.error("Failed to save invoice.")
        else:
            st.error("Failed to extract invoice data.")
