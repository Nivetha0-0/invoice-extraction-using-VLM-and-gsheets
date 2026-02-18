import os
import json
import base64
import fitz
from PIL import Image
from io import BytesIO
from groq import Groq
import streamlit as st

# ===============================
# CONFIG
# ===============================

st.set_page_config(
    page_title="Invoice OCR & Structured Extraction",
    page_icon="📄",
    layout="wide"
)

client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# ===============================
# OCR FUNCTIONS
# ===============================

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
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                },
                {
                    "type": "text",
                    "text": "Extract all text exactly as seen. No explanation."
                }
            ]
        }],
        temperature=0
    )

    return response.choices[0].message.content.strip()


def extract_invoice_fields(text):

    prompt = f"""
Return ONLY valid JSON.
No markdown.
No explanation.

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

    raw_output = extract_invoice_fields(full_text)

    try:
        return json.loads(raw_output)
    except:
        st.error("JSON parsing failed. Raw output below:")
        st.code(raw_output)
        return None

# ===============================
# UI
# ===============================

st.title("📄 Invoice OCR & Structured Data Extraction")

uploaded_file = st.file_uploader(
    "Upload PDF or Image",
    type=["pdf", "png", "jpg", "jpeg"]
)

if uploaded_file:

    if st.button("🚀 Extract & Parse"):

        with st.spinner("Processing..."):
            result = process_document(uploaded_file)

        if result:
            st.success("Extraction Successful")
            st.json(result)
        else:
            st.error("Extraction Failed")
