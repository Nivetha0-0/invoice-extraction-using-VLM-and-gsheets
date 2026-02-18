import json
import fitz
import base64
from PIL import Image
from io import BytesIO
from groq import Groq
import streamlit as st
import gspread

# ======================================================
# PAGE CONFIG
# ======================================================
st.set_page_config(
    page_title="Invoice OCR & GSheets",
    page_icon="📄",
    layout="wide",
)

# ======================================================
# LOAD GROQ API KEY
# ======================================================
groq_api_key = st.secrets["GROQ_API_KEY"]
client = Groq(api_key=groq_api_key)

# ======================================================
# OCR / JSON EXTRACTION
# ======================================================
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
    return base64.b64encode(buffer.getvalue()).decode()

def extract_text_with_vision(image):
    base64_image = image_to_base64(image)

    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                {"type": "text", "text": "Extract all text exactly as seen. No explanation."}
            ],
        }],
        temperature=0,
    )
    
    return response.choices[0].message.content.strip()

def extract_invoice_fields(text):
    prompt = f"""
Return ONLY valid JSON (no markdown or explanation).

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
        temperature=0,
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

    raw_output = extract_invoice_fields(full_text)
    
    # clean JSON
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1]

    try:
        return json.loads(cleaned)
    except:
        st.error("JSON parsing failed")
        st.code(cleaned)
        return None

# ======================================================
# GOOGLE SHEETS FUNCTIONS
# ======================================================
def get_gsheet(sheet_name):
    try:
        credentials_dict = st.secrets["gcp_service_account"]
        gc = gspread.service_account_from_dict(credentials_dict)
        sh = gc.open(sheet_name)
        return sh.sheet1
    except Exception as e:
        st.error(f"Unable to connect Google Sheets: {e}")
        return None

def get_service_account_email():
    try:
        return st.secrets["gcp_service_account"]["client_email"]
    except:
        return None

def save_invoice_to_sheet(sheet, data):

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
        payment.get("IFSCCode"),
    ]

    try:
        sheet.append_row(row)
        return True
    except Exception as e:
        st.error(f"Error writing to sheet: {e}")
        return False

# ======================================================
# UI
# ======================================================

st.title("📄 Invoice OCR & Google Sheets")

uploaded_file = st.file_uploader(
    "Upload PDF or Image Invoice",
    type=["pdf","png","jpg","jpeg"]
)

# ─── PREVIEW & EXTRACT BUTTON ─────────────────────────────────
if uploaded_file:

    col1, col2 = st.columns([1,1])

    with col1:
        st.subheader("Preview")
        if uploaded_file.name.lower().endswith(".pdf"):
            try:
                pages = pdf_to_images(uploaded_file)
                if pages:
                    st.image(pages[0], caption="Page 1", use_column_width=True)
            except:
                st.info("PDF preview not available")
        else:
            st.image(uploaded_file, use_column_width=True)

    with col2:
        st.subheader("File Details")
        st.write("Name:", uploaded_file.name)
        st.write("Size:", f"{len(uploaded_file.getvalue())/1024:.1f} KB")

        if st.button("🚀 Extract & Parse"):
            with st.spinner("Extracting..."):
                result = process_document(uploaded_file)
            
            if result:
                st.session_state["parsed_invoice"] = result
                st.success("✅ Extraction Complete")
            else:
                st.error("❌ Extraction Failed")

# ─── SHOW RESULTS + SAVE TO SHEETS ──────────────────────────
if "parsed_invoice" in st.session_state:

    st.markdown("---")
    st.subheader("Extracted Invoice JSON")
    st.json(st.session_state["parsed_invoice"])

    sheet_name = st.text_input(
        "Google Sheet Name",
        value="invoice-corrected"
    )

    sa_email = get_service_account_email()
    #if sa_email:
    #    st.info(f"Share the spreadsheet with: {sa_email} (Editor)")

    if st.button("💾 Save to Google Sheets"):
        sheet = get_gsheet(sheet_name)
        if sheet:
            success = save_invoice_to_sheet(sheet, st.session_state["parsed_invoice"])
            if success:
                st.success("✅ Invoice saved successfully!")
            else:
                st.error("❌ Save to Google Sheets failed")
        else:
            st.error("❌ Could not open specified sheet")
