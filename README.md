# 📄 Invoice OCR & Structured Data Extraction Using VLM and LLM to gsheet

A Streamlit-based web application that extracts structured invoice data from PDFs and images using Vision LLM and automatically stores the results in Google Sheets.


## WORKFLOW

1. User uploads invoice
2. PDF converted to images (if needed)
3. Vision model extracts raw text
4. LLM converts text → structured JSON
5. Data displayed in UI
6. User saves structured data to Google Sheets

## Tech Stack

* **Frontend/UI**: Streamlit
* **Vision Language Model(VLM)**: llama-4-scout-17b-16e-instruct via Groq 
* **LLM Structured Extraction**: lama-3.1-8b-instant via Groq
* **Cloud Deployment**: Streamlit Cloud
* **Storage**: Google Sheets API
* **PDF Processing**: PyMuPDF (fitz)
* **Image Handling**: Pillow

## Project Structure

invoice-extraction-using-VLM-and-gsheets/
│
├── app.py
├── requirements.txt
└── README.md

## Extracted Fields

The app extracts the following structured data:

### Vendor

* Business Name
* Address
* GSTIN
* Phone
* Email

### Buyer

* Name
* Billing Address
* Shipping Address
* GSTIN
* Phone
* Email

### Totals

* Grand Total

### Payment Details

* Mode of Payment
* Bank Name
* Account Number
* IFSC Code

## Setup Instructions

### Clone the Repository

```bash
git clone https://github.com/your-username/invoice-ocr-gsheets.git
cd invoice-ocr-gsheets
```

---

### Install Dependencies

```bash
pip install -r requirements.txt
```

If you don't have a `requirements.txt`, generate one:

```bash
pip freeze > requirements.txt
```

---

### Add Streamlit Secrets

Create `.streamlit/secrets.toml` locally **or** configure in Streamlit Cloud.

```toml
GROQ_API_KEY = "your_groq_api_key_here"

[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "your-cert-url"
```

---

### 4️⃣ Run the App

```bash
streamlit run app.py
```

---

## Deploy on Streamlit Cloud

1. Push your code to GitHub
2. Go to Streamlit Cloud
3. Create a new app
4. Add your `GROQ_API_KEY` and `gcp_service_account` in Secrets
5. Deploy 🚀

---

## Google Sheets Setup

* Create a Google Sheet
* Copy the sheet name
* Share the sheet with your service account email (Editor access)
* Paste the sheet name inside the app
* Click **Save to Google Sheets**

---

## Possible extensions

* Add duplicate invoice detection
* Multi-page PDF preview slider
* Bulk upload support
* Look into REST API backend version

---

Just tell me what you need next 🚀
