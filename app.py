import os
import json
import fitz
import base64
from PIL import Image
from io import BytesIO
from groq import Groq
from dotenv import load_dotenv
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials

# -----------------------
# Load API Key
# -----------------------
load_dotenv()
groq_api_key = os.getenv("GROQ_API_KEY")
if not groq_api_key:
    raise ValueError("Set the GROQ_API_KEY in a .env file")

client = Groq(api_key=groq_api_key)

# -----------------------
# Helper Functions
# -----------------------

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
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}} ,
                {"type": "text", "text": vision_prompt}
            ],
        }],
        temperature=0
    )
    return response.choices[0].message.content.strip()

def extract_invoice_fields(text):
    prompt = f"""
Extract structured invoice data from the text below. Do not explain or hallucinate

Return exactly this JSON schema with values or null if missing:

{{
"Vendor":{{"BusinessName":null,"Address":null,"GSTIN":null,"Phone":null,"Email":null}},
"Buyer":{{"Name":null,"BillingAddress":null,"ShippingAddress":null,"GSTIN":null,"Phone":null,"Email":null}},
"Items":[{{"Description":null,"Quantity":null,"Unit":null,"RatePerUnit":null,"Discount":null,
"GSTRatePercent":null,"CGSTAmount":null,"SGSTAmount":null,"TotalItemAmount":null}}],
"Totals":{{"Subtotal":null,"TotalTaxableValue":null,"TotalCGST":null,"TotalSGST":null,
"RoundOff":null,"GrandTotal":null,"AmountInWords":null}},
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

def process_llm_output(llm_output, threshold=0.6):
    try:
        data = json.loads(llm_output)
    except:
        st.error("Invalid JSON returned from LLM")
        return None
    return data

def process_document(uploaded_file):
    full_text = ""
    filename = uploaded_file.name.lower()
    uploaded_file.seek(0)

    if filename.endswith(".pdf"):
        images = pdf_to_images(uploaded_file)
        for img in images:
            full_text += extract_text_with_vision(img) + "\n"
    else:
        image = Image.open(uploaded_file).convert("RGB")
        full_text = extract_text_with_vision(image)

    llm_output = extract_invoice_fields(full_text)
    structured_data = process_llm_output(llm_output)
    return structured_data

# -----------------------
# Google Sheets Integration
# -----------------------

def get_gsheet(sheet_name, credentials_file="service_account.json"):
    """
    Get a Google Sheets worksheet using a service account JSON file.
    """
    try:
        gc = gspread.service_account(filename=credentials_file)
    except Exception as e:
        raise RuntimeError(f"Failed to load service account credentials: {e}")

    try:
        # Open spreadsheet by title, URL, or key
        if ("https://" in sheet_name) or (len(sheet_name) > 30 and " " not in sheet_name):
            try:
                sh = gc.open_by_key(sheet_name)
            except Exception:
                sh = gc.open_by_url(sheet_name)
        else:
            try:
                sh = gc.open(sheet_name)
            except Exception:
                sh = gc.open_by_key(sheet_name)
        return sh.sheet1
    except Exception as e:
        raise RuntimeError(f"Could not open spreadsheet '{sheet_name}': {e}")

def get_service_account_email(credentials_file="service_account.json"):
    """Return the service account email from the JSON file for sharing the sheet."""
    try:
        with open(credentials_file, "r", encoding="utf-8") as f:
            info = json.load(f)
        return info.get("client_email")
    except Exception as e:
        raise RuntimeError(f"Unable to read service account email: {e}")

def save_invoice_to_sheet(sheet, data):
    """
    Flatten simplified invoice fields and append as a row starting at column A.
    """
    vendor = data.get("Vendor", {})
    buyer = data.get("Buyer", {})
    totals = data.get("Totals", {})
    payment = data.get("PaymentDetails", {})

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
        payment.get("IFSCCode")
    ]

    try:
        next_row = len(sheet.get_all_values()) + 1
        sheet.update(f"A{next_row}", [row])
        return True
    except Exception as e:
        print("Error saving to sheet:", repr(e))
        return False

# -----------------------
# Streamlit UI
# -----------------------

st.title("Invoice OCR & Structured Data Extraction")

uploaded_file = st.file_uploader("Upload PDF or Image", type=["pdf", "png", "jpg", "jpeg"])

if uploaded_file:
    with st.spinner("Processing document..."):
        result = process_document(uploaded_file)

    if result:
        st.subheader("Extracted Invoice Data")
        st.json(result)

        # Let user provide a sheet name, URL, or spreadsheet ID
        sheet_input = st.text_input("Google Sheet name, ID, or URL", value="Invoices")
        creds_file = "service_account.json"
        try:
            sa_email = get_service_account_email(creds_file)
        except Exception:
            sa_email = None

        if sa_email:
            st.info(f"Share the spreadsheet with the service account: {sa_email} (Editor)")

        if st.button("Save to Google Sheets"):
            try:
                sheet = get_gsheet(sheet_input, credentials_file=creds_file)
                success = save_invoice_to_sheet(sheet, result)
                if success:
                    st.success("Invoice data saved to Google Sheets!")
                else:
                    st.error("Failed to save to Google Sheets. Check logs.")
            except Exception as e:
                st.error(f"Error connecting to Google Sheets: {repr(e)}")
                st.exception(e)
    else:
        st.error("Failed to extract invoice data.")
