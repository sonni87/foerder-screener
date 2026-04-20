import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber

# 🔥 FLEXIBLE & PRAXISTAUGLICHE PATTERNS
PATTERNS = [

    # 🔹 pro / je Kombination
    r"(ein|eine|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt).*?(pro|je)\s+(Hochschule|Einrichtung|Institution|Universität)",
    r"(pro|je)\s+(Hochschule|Einrichtung|Institution|Universität).*?(ein|eine|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",

    # 🔹 Mengenbegrenzung
    r"(nur|maximal|max\.|höchstens|nicht mehr als).*?(ein|eine|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben)",

    # 🔹 Einreichung
    r"(kann|darf).*?(nur\s*)?(ein|eine|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben).*?(eingereicht|gestellt)",

    # 🔹 Beschränkung
    r"(beschränkt|begrenzt).*?(ein|eine)\s+(Antrag|Skizze|Projektskizze)",

    # 🔹 Vorauswahl (sehr wichtig!)
    r"(hochschulinterne|interne|institutionelle).*?(Vorauswahl|Auswahlverfahren)",

    # 🔹 Englisch
    r"(one|1)\s+(proposal|application).*?(per)\s+(institution|university)",
    r"(only|maximum).*?(one)\s+(proposal|application)"
]

# ❌ Ausschlüsse (gegen False Positives)
EXCLUDE = [
    "Antragstellung",
    "Antragsteller",
    "Antragsverfahren",
    "Euro",
    "€",
    "Reise",
    "Budget",
    "Laufzeit"
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
        r = requests.get(url, timeout=25, headers=headers)
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

        # 🔥 PDF-Fix (entscheidend!)
        text = text.replace("-\n", "")
        text = text.replace("\n", " ")

        return text, title

    except Exception as e:
        return f"ERROR: {str(e)}", "Fehler beim Laden"

# 🧠 ZITATE FINDEN
def extract_quotes(text):
    results = []

    for pattern in PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):

            snippet = text[max(0, m.start()-120):m.end()+120]

            # ❌ irrelevante Treffer raus
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

        if text.startswith("ERROR"):
            status = "Nicht prüfbar"
            quote = text
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

    # 📥 CSV Export
    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "📥 CSV herunterladen",
        csv,
        "foerder_screening.csv",
        "text/csv"
    )
