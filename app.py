import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber

# 🔍 SUCHMUSTER (deine Version)
PATTERNS = [
    r"pro Hochschule.*?nur ein Antrag",
    r"nur ein Antrag",
    r"maximal ein",
    r"nicht mehr als"
]

# 🔧 BMFTR FIX
def transform_url(url):
    if "bmftr.bund.de/SharedDocs/Bekanntmachungen" in url:
        return url.split("?")[0] + "?view=renderNewsletterHtml"
    return url

# 🌐 CONTENT LADEN (stabile Version)
def get_content(url):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()

        # PDF
        if url.endswith(".pdf"):
            with pdfplumber.open(BytesIO(r.content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                title = text.split("\n")[0] if text else "PDF ohne Titel"

        # HTML
        else:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ")
            title = soup.title.string if soup.title else url

        return text, title

    except Exception:
        return "ERROR", "Fehler beim Laden"

# 🧠 ZITATE FINDEN
def extract_quotes(text):
    results = []

    for pattern in PATTERNS:
        matches = re.finditer(pattern, text, re.IGNORECASE)

        for m in matches:
            start = max(0, m.start() - 120)
            end = min(len(text), m.end() + 120)
            snippet = text[start:end]

            # 👉 Markierung wie früher (>>> <<<)
            snippet = snippet.replace(m.group(0), f">>>{m.group(0)}<<<")

            results.append(snippet.strip())

    return "\n\n".join(results)

# 🎯 APP
st.title("🔍 Förder-Screener")

urls = st.text_area("URLs (eine pro Zeile)")

if st.button("Start"):

    results = []

    for i, url in enumerate(urls.split("\n"), 1):
        if not url.strip():
            continue

        fixed_url = transform_url(url)
        text, title = get_content(fixed_url)

        if text == "ERROR":
            status = "Nicht prüfbar"
            quote = ""
        else:
            quote = extract_quotes(text)

            if quote:
                status = "JA – TREFFER"
            else:
                status = "Keine Beschränkung"

        results.append({
            "Nr": i,
            "Titel": title,
            "URL": url,
            "Status": status,
            "Zitat": quote
        })

    df = pd.DataFrame(results)

    # Anzeige
    st.dataframe(df, use_container_width=True)

    # 📥 CSV Export (stabil!)
    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "📥 CSV herunterladen",
        csv,
        "foerder_screening.csv",
        "text/csv"
    )
