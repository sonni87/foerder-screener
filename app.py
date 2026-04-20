import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber

PATTERNS = [
    r"\bpro\s+(Hochschule|Einrichtung|Institution)\b",
    r"\bnur\s+ein(en|e)?\s+(Antrag|Einzelantrag)\b",
    r"\bmaximal\s+ein(en|e)?\b",
    r"\bnicht\s+mehr\s+als\b"
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

def extract(text):
    for pattern in PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            start = max(m.start()-100,0)
            end = min(m.end()+100,len(text))
            snippet = text[start:end]
            return re.sub(m.group(0), f"🔴 {m.group(0)}", snippet, flags=re.IGNORECASE)
    return ""

st.title("🔍 Förder-Screener")

urls = st.text_area("URLs (eine pro Zeile)")

if st.button("Start"):
    results = []

    for url in urls.split("\n"):
        if not url.strip():
            continue

        text, title = get_content(transform_url(url))

        if text == "ERROR":
            status = "Nicht prüfbar"
            quote = ""
        else:
            quote = extract(text)
            status = "Treffer" if quote else "Keine Beschränkung"

        results.append({
            "Titel": title,
            "URL": url,
            "Status": status,
            "Zitat": quote
        })

    df = pd.DataFrame(results)
    st.dataframe(df)
