import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber

# 🔍 ALLE FORMULIERUNGEN EXPLIZIT

PATTERNS = [

    # --- PRO / JE ---
    r"pro Hochschule.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"je Hochschule.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"pro Einrichtung.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"je Einrichtung.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"pro Institution.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"je Institution.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"pro Forschungseinrichtung.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"je Forschungseinrichtung.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"pro Universität.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"je Universität.*?(ein|eine|einen|1)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",

    # --- MENGE ---
    r"nur\s+(ein|eine|einen)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"maximal\s+(ein|eine|einen)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"max\.\s*(ein|eine|einen)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"höchstens\s+(ein|eine|einen)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",
    r"nicht mehr als\s+(ein|eine|einen)\s+(Antrag|Skizze|Projektskizze|Vorhaben|Projekt)",

    # --- UMGEKEHRT ---
    r"(ein|eine)\s+(Antrag|Skizze|Projektskizze|Vorhaben).*?je Hochschule",
    r"(ein|eine)\s+(Antrag|Skizze|Projektskizze|Vorhaben).*?pro Hochschule",
    r"(ein|eine)\s+(Antrag|Skizze|Projektskizze|Vorhaben).*?je Einrichtung",
    r"(ein|eine)\s+(Antrag|Skizze|Projektskizze|Vorhaben).*?pro Einrichtung",
    r"(ein|eine)\s+(Antrag|Skizze|Projektskizze|Vorhaben).*?je Institution",

    # --- EINREICHUNG ---
    r"kann nur\s+(ein|eine)\s+(Antrag|Skizze|Projektskizze|Vorhaben)\s+eingereicht werden",
    r"darf nur\s+(ein|eine)\s+(Antrag|Skizze|Projektskizze|Vorhaben)\s+eingereicht werden",
    r"kann\s+(ein|eine)\s+(Antrag|Skizze|Projektskizze|Vorhaben)\s+gestellt werden.*?(pro|je)",

    # --- BESCHRÄNKUNG ---
    r"Einreichung.*?beschränkt.*?(ein|eine)\s+(Antrag|Skizze)",
    r"Beteiligung.*?beschränkt.*?(ein|eine)\s+(Antrag|Skizze)",
    r"nur\s+(ein|eine)\s+(Antrag|Skizze)\s+pro Hochschule zulässig",
    r"nur\s+(ein|eine)\s+(Antrag|Skizze)\s+pro Einrichtung zulässig",

    # --- VORAUSWAHL ---
    r"hochschulinterne Vorauswahl",
    r"internes Auswahlverfahren",
    r"institutionelle Vorauswahl",
    r"Pre-selection",
    r"internal selection",

    # --- ENGLISCH ---
    r"one proposal per institution",
    r"only one application",
    r"maximum one proposal",
    r"per university only one application",
    r"not more than one proposal"
]

# ❌ Ausschlüsse
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

# 🌐 CONTENT
def get_content(url):
    try:
        url = transform_url(url)
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, timeout=25, headers=headers)
        r.raise_for_status()

        if url.endswith(".pdf"):
            with pdfplumber.open(BytesIO(r.content)) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
                title = text.split("\n")[0] if text else "PDF ohne Titel"
        else:
            soup = BeautifulSoup(r.text, "html.parser")
            text = soup.get_text(" ")
            title = soup.title.string if soup.title else url

        # PDF Fix
        text = text.replace("-\n", "")
        text = text.replace("\n", " ")

        return text, title

    except Exception as e:
        return f"ERROR: {str(e)}", "Fehler beim Laden"

# 🧠 MATCHING
def extract_quotes(text):
    results = []

    for pattern in PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):

            snippet = text[max(0, m.start()-120):m.end()+120]

            if any(word.lower() in snippet.lower() for word in EXCLUDE):
                continue

            snippet = re.sub(
                re.escape(m.group(0)),
                f">>>{m.group(0)}<<<",
                snippet,
                flags=re.IGNORECASE
            )

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

        text, title = get_content(url)

        if text.startswith("ERROR"):
            status = "Nicht prüfbar"
            quote = text
        else:
            quote = extract_quotes(text)
            status = "JA – TREFFER" if quote else "Keine Beschränkung"

        results.append({
            "Nr": i,
            "Titel": title,
            "URL": url,
            "Status": status,
            "Zitat": quote
        })

    df = pd.DataFrame(results)

    st.dataframe(df, use_container_width=True)

    csv = df.to_csv(index=False).encode("utf-8")

    st.download_button(
        "📥 CSV herunterladen",
        csv,
        "foerder_screening.csv",
        "text/csv"
    )
