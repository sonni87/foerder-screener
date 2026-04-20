import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber

# 🎯 PRÄZISE MUSTER
PATTERNS = [
    r"pro Hochschule.*?nur ein Antrag",
    r"nur ein Antrag",
    r"maximal ein",
    r"nicht mehr als.*?ein",
]

def transform_url(url):
    if "bmftr.bund.de/SharedDocs/Bekanntmachungen" in url:
        return url.split("?")[0] + "?view=renderNewsletterHtml"
    return url

def get_content(url):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()

        if url.endswith(".pdf"):
            with pdfplumber.open(BytesIO(r.content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                title = text.split("\n")[0]
        else:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ")
            title = soup.title.string if soup.title else url

        return text, title
    except:
        return "ERROR", "Fehler"

# 🎯 NUR GANZE SÄTZE EXTRAHIEREN
def extract_sentence(text):
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for sentence in sentences:
        for pattern in PATTERNS:
            if re.search(pattern, sentence, re.IGNORECASE):
                return sentence.strip()

    return ""

# 🎯 APP
st.title("🔍 Förder-Screener")

urls = st.text_area("URLs (eine pro Zeile)")

if st.button("Start"):

    results = []

    for i, url in enumerate(urls.split("\n"), 1):
        if not url.strip():
            continue

        fixed = transform_url(url)
        text, title = get_content(fixed)

        if text == "ERROR":
            status = "⚠️ Nicht prüfbar"
            quote = ""
        else:
            quote = extract_sentence(text)

            if quote:
                status = "⚠️ JA"
            else:
                status = "✅ Nein"

        results.append({
            "Nr": i,
            "Titel": title,
            "URL": url,
            "Status": status,
            "Relevanter Satz": quote
        })

    df = pd.DataFrame(results)

    # 🔥 SAUBERE TABELLE
    st.dataframe(df, use_container_width=True)

    # 🔥 RICHTIGER EXCEL EXPORT
    excel = df.to_excel(index=False, engine='openpyxl')

    st.download_button(
        "📥 Excel herunterladen",
        excel,
        "foerder_screening.xlsx"
    )
