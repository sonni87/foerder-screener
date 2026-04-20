import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber
import time

# 🎯 NUR ECHTE BESCHRÄNKUNGEN
PATTERNS = [
    r"pro Hochschule.*?nur ein Antrag",
    r"je Hochschule.*?nur ein Antrag",
    r"nur ein Antrag",
    r"maximal ein Antrag",
    r"höchstens ein Antrag",
    r"eine Projektskizze je",
    r"nur eine Skizze",
]

# ❌ IRRELEVANTE TREFFER (rausfiltern!)
EXCLUDE = [
    "Reise",
    "Euro",
    "Fördersumme",
    "Projektkosten",
    "Budget",
    "Mittel",
    "Zuwendung",
    "Laufzeit",
]

# 🔧 URL FIX
def transform_url(url):
    if "bmftr.bund.de/SharedDocs/Bekanntmachungen" in url:
        return url.split("?")[0] + "?view=renderNewsletterHtml"
    return url

# 🌐 ROBUSTES LADEN (inkl. Retry)
def fetch(url):
    headers = {"User-Agent": "Mozilla/5.0"}

    for attempt in range(2):
        try:
            r = requests.get(url, timeout=25, headers=headers)
            r.raise_for_status()
            return r
        except:
            time.sleep(2)

    raise Exception("Request failed")

# 📄 CONTENT
def get_content(url):
    try:
        url = transform_url(url)
        r = fetch(url)

        # PDF
        if url.endswith(".pdf"):
            with pdfplumber.open(BytesIO(r.content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)

                if not text.strip():
                    return "ERROR: PDF leer", "Fehler"

                title = text.split("\n")[0]
                return text, title

        # HTML
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ")

        if len(text) < 500:
            return "ERROR: Seite leer", "Fehler"

        title = soup.title.string.strip() if soup.title else url
        return text, title

    except Exception as e:
        return f"ERROR: {str(e)}", "Fehler beim Laden"

# 🧠 RELEVANTE SÄTZE
def extract_sentence(text):
    sentences = re.split(r'(?<=[.!?])\s+', text)

    for sentence in sentences:
        # ❌ irrelevante Sätze überspringen
        if any(word.lower() in sentence.lower() for word in EXCLUDE):
            continue

        for pattern in PATTERNS:
            if re.search(pattern, sentence, re.IGNORECASE):

                highlighted = re.sub(
                    pattern,
                    lambda m: f"🔴 {m.group(0)}",
                    sentence,
                    flags=re.IGNORECASE
                )

                return highlighted.strip()

    return ""

# 🎯 UI
st.title("🔍 Förder-Screener")

urls = st.text_area("URLs (eine pro Zeile)")

if st.button("Start"):

    results = []

    for i, url in enumerate(urls.split("\n"), 1):
        if not url.strip():
            continue

        text, title = get_content(url)

        if text.startswith("ERROR"):
            status = "⚠️ Nicht prüfbar"
            quote = text
        else:
            quote = extract_sentence(text)

            if quote:
                status = "⚠️ JA – Beschränkung"
            else:
                status = "✅ Keine Beschränkung"

        results.append({
            "Nr": i,
            "Titel": title,
            "URL": url,
            "Status": status,
            "Relevanter Satz": quote
        })

    df = pd.DataFrame(results)

    # 📊 Anzeige
    st.dataframe(df, use_container_width=True)

    # 📥 Excel Export
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine='openpyxl')

    st.download_button(
        "📥 Excel herunterladen",
        buffer.getvalue(),
        "foerder_screening.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
