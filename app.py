import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber

# 🔍 ERWEITERTE PATTERNS (mit Wortgrenzen!)
PATTERNS = [
    r"\b(nur|maximal|höchstens)?\s*\b(ein|eine|einen|1)\b\s+\b(Antrag|Projektantrag|Förderantrag|Skizze|Projektskizze|Vorhaben)\b",
    r"\b(ein|eine|1)\b\s+\b(Antrag|Projektantrag|Skizze|Projektskizze|Vorhaben)\b.*?\b(pro|je)\b\s+\b(Hochschule|Einrichtung|Institution)\b",
    r"\b(pro|je)\b\s+\b(Hochschule|Einrichtung|Institution)\b.*?\b(ein|eine|1)\b\s+\b(Antrag|Projektantrag|Skizze|Projektskizze|Vorhaben)\b"
]

# ❌ Ausschluss von falschen Treffern
EXCLUDE = [
    "Antragstellung",
    "Antragsteller",
    "Antragsverfahren"
]

# 🔧 BMFTR FIX
def transform_url(url):
    if "bmftr.bund.de/SharedDocs/Bekanntmachungen" in url:
        return url.split("?")[0] + "?view=renderNewsletterHtml"
    return url

# 🌐 CONTENT LADEN
def get_content(url):
    try:
        url = transform_url(url)

        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, timeout=20, headers=headers)
        r.raise_for_status()

        # 📄 PDF
        if url.endswith(".pdf"):
            with pdfplumber.open(BytesIO(r.content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                title = text.split("\n")[0] if text else "PDF ohne Titel"

        # 🌐 HTML
        else:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ")
            title = soup.title.string if soup.title else url

        # 🔥 Zeilenumbrüche entfernen (wichtig für PDFs!)
        text = text.replace("\n", " ")

        return text, title

    except Exception:
        return "ERROR", "Fehler beim Laden"

# 🧠 ZITATE FINDEN
def extract_quotes(text):
    results = []

    for pattern in PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):

            snippet = text[max(0, m.start()-120):m.end()+120]

            # ❌ irrelevante Treffer rausfiltern
            if any(word.lower() in snippet.lower() for word in EXCLUDE):
                continue

            # 🔴 Highlight
            snippet = re.sub(
                re.escape(m.group(0)),
                f">>>{m.group(0)}<<<",
                snippet,
                flags=re.IGNORECASE
            )

            results.append(snippet.strip())

    return "\n\n".join(results)

# 🎯 STREAMLIT APP
st.title("🔍 Förder-Screener")

urls = st.text_area("URLs (eine pro Zeile)")

if st.button("Start"):

    results = []

    for i, url in enumerate(urls.split("\n"), 1):
        if not url.strip():
            continue

        text, title = get_content(url)

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

    # 📊 Anzeige
    st.dataframe(df, use_container_width=True)

    # 📥 CSV Export (stabil)
    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "📥 CSV herunterladen",
        csv,
        "foerder_screening.csv",
        "text/csv"
    )
