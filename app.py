import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber


# =============================================================================
# PATTERNS
# -----------------------------------------------------------------------------
# Wichtige Änderungen gegenüber der alten Version:
#   1. Alle Keywords mit Wortgrenzen \b – sonst matcht "interne" in "Internet".
#   2. Begrenzte Distanz zwischen Keywords (z. B. {0,80}?) – sonst matcht das
#      Pattern über ganze Absätze hinweg und erzeugt False Positives.
#   3. Mehr Formulierungsvarianten: "Projektbeteiligung", "Zuwendung",
#      "Mehrfachantragstellung", "je antragstellende Einrichtung",
#      Zahlwörter 1–3 (für "maximal zwei Skizzen" etc.).
# =============================================================================
PATTERNS = [
    # "pro/je Einrichtung ... (nur|maximal|...) ... Antrag/Skizze/..."
    (
        r"\b(pro|je)\s+(Hochschule|Einrichtung|Institution|Universit(ä|ae)t|"
        r"antragstellende[rn]?\s+(Einrichtung|Hochschule|Institution)|Antragsteller(in)?)\b"
        r".{0,80}?\b(ein|eine|1|zwei|2|drei|3|maximal|max\.|h(ö|oe)chstens|nur|nicht mehr als)\b"
        r".{0,40}?\b(Antrag|Antr(ä|ae)ge|Skizze|Skizzen|Projektskizze|Projektskizzen|"
        r"Projektbeteiligung|Vorhaben|Projekt|Projekte|Vorhabenbeschreibung|Zuwendung)\b",
        "pro/je Einrichtung"
    ),

    # "(nur|maximal|höchstens|...) ... ein/eine/X ... Antrag/Skizze/..."
    (
        r"\b(nur|maximal|max\.|h(ö|oe)chstens|nicht mehr als|lediglich)\b"
        r".{0,60}?\b(ein|eine|1|zwei|2|drei|3)\b"
        r".{0,20}?\b(Antrag|Antr(ä|ae)ge|Skizze|Skizzen|Projektskizze|Projektskizzen|"
        r"Projektbeteiligung|Vorhaben|Projekt|Projekte|Vorhabenbeschreibung)\b",
        "Mengenbegrenzung"
    ),

    # "Eine/Jede/Pro Hochschule (darf|kann) ... (nicht mehr als|nur|maximal) ..."
    (
        r"\b(Eine|Jede[rs]?|Je|Pro)\s+(Hochschule|Einrichtung|Institution|"
        r"Universit(ä|ae)t|Antragsteller(in)?)\b"
        r".{0,60}?\b(darf|kann|soll|wird)\b"
        r".{0,80}?\b(nicht mehr als|maximal|max\.|nur|h(ö|oe)chstens)\b"
        r".{0,40}?\b(ein|eine|einen|1|zwei|2|drei|3)\b"
        r".{0,40}?\b(Antrag|Skizze|Projekt|Vorhaben|Projektbeteiligung|Zuwendung)",
        "Einrichtung darf nur"
    ),

    # "Einrichtungen/Hochschulen können/dürfen ... nicht mehr als ..."
    (
        r"\b(Einrichtungen|Hochschulen|Universit(ä|ae)ten)\b"
        r".{0,40}?\b(k(ö|oe)nnen|d(ü|ue)rfen)\b"
        r".{0,60}?\b(nicht mehr als|maximal|max\.|nur|h(ö|oe)chstens)\b"
        r".{0,40}?\b(ein|eine|einen|1|zwei|2|drei|3)\b"
        r".{0,40}?\b(Zuwendung|Antrag|Skizze|Projekt|Vorhaben|Projektbeteiligung)",
        "Plural Einrichtungen"
    ),

    # Mehrfachantragstellung ist ausgeschlossen
    (
        r"\b(Mehrfachantrag|Mehrfachantragstellung|Mehrfacheinreichung|"
        r"mehrere\s+Antr(ä|ae)ge|mehrere\s+Skizzen|mehr als eine\s+(Skizze|Antrag))\b"
        r".{0,80}?\b(nicht|aus(-?\s*)?geschlossen|unzul(ä|ae)ssig|nicht zul(ä|ae)ssig|"
        r"nicht m(ö|oe)glich|nicht gestattet|ausgeschlossen)\b",
        "Mehrfachantragstellung"
    ),

    # "beschränkt/begrenzt auf X Anträge/Skizzen"
    (
        r"\b(beschr(ä|ae)nkt|begrenzt|Begrenzung|Beschr(ä|ae)nkung)\b"
        r".{0,40}?\bauf\s+(ein|eine|1|zwei|2|drei|3|maximal)\b"
        r".{0,40}?\b(Antrag|Antr(ä|ae)ge|Skizze|Skizzen|Projektskizze|"
        r"Projektskizzen|Projektbeteiligung)\b",
        "Begrenzung auf Anzahl"
    ),

    # Hochschulinterne Vorauswahl (MIT Wortgrenzen – damit "Internet" NICHT matcht)
    (
        r"\b(hochschulintern|institutionsintern|universit(ä|ae)tsintern)(e|er|es|en)?\b"
        r".{0,40}?\b(Vorauswahl|Auswahlverfahren|Priorisierung|Abstimmung)\b",
        "Interne Vorauswahl"
    ),

    # Englisch
    (
        r"\b(only one|maximum of one|at most one|one)\b\s+"
        r"(proposal|application|submission)\b"
        r".{0,40}?\b(per|by each)\s+(institution|university|applicant|organisation|organization)\b",
        "EN: one per institution"
    ),
    (
        r"\b(multiple|more than one)\b\s+(proposals|applications|submissions)\b"
        r".{0,40}?\b(not allowed|not permitted|excluded|prohibited)\b",
        "EN: multiple not allowed"
    ),
]


# =============================================================================
# URL-Transformation
# =============================================================================
def transform_url(url: str) -> str:
    """BMFTR-Bekanntmachungen sauberer rendern (reiner Content statt Portal-UI)."""
    if "bmftr.bund.de/SharedDocs/Bekanntmachungen" in url:
        return url.split("?")[0] + "?view=renderNewsletterHtml"
    return url


# =============================================================================
# PDF-Erkennung per Content-Type / Magic Bytes (NICHT per URL-Endung!)
# -----------------------------------------------------------------------------
# Die alte Version prüfte nur url.endswith(".pdf"). Dadurch wurden Links wie
#   projekttraeger.dlr.de/de/media/929/download
#   daad.de/.../file.php?id=6993
# fälschlich als HTML geparst, obwohl es PDFs sind.
# =============================================================================
def is_pdf_content(response) -> bool:
    ct = response.headers.get("content-type", "").lower()
    if "pdf" in ct:
        return True
    return response.content[:4] == b"%PDF"


def clean_pdf_text(text: str) -> str:
    """PDF-Cleanup: Silbentrennung auflösen, Whitespace normalisieren,
    CID-Encoding-Problem sichtbar machen."""
    # CID-Erkennung: Wenn viele (cid:xxx)-Tokens, ist der Text de facto unlesbar
    cid_count = len(re.findall(r"\(cid:\d+\)", text))
    total_len = max(len(text), 1)
    if cid_count > 20 and (cid_count * 8) / total_len > 0.05:
        text = (
            "[⚠️ HINWEIS: Dieses PDF verwendet CID-kodierte Fonts. "
            "Textextraktion nur eingeschränkt möglich – bitte manuell prüfen.] "
            + text
        )
    text = re.sub(r"-\s*\n\s*", "", text)      # Silbentrennung am Zeilenende
    text = re.sub(r"\s+", " ", text)            # Whitespace kollabieren
    return text


# =============================================================================
# Content-Fetch mit Retry und realistischem User-Agent
# =============================================================================
def get_content(url: str, retries: int = 2):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    url_fetch = transform_url(url)
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.get(url_fetch, timeout=30, headers=headers, allow_redirects=True)
            r.raise_for_status()

            if is_pdf_content(r):
                with pdfplumber.open(BytesIO(r.content)) as pdf:
                    text = "\n".join((p.extract_text() or "") for p in pdf.pages)
                text = clean_pdf_text(text)
                first_line = next(
                    (ln for ln in text.split(" ") if ln.strip()), "PDF"
                )
                title = " ".join(text.split()[:10])[:100] or "PDF ohne Titel"
            else:
                soup = BeautifulSoup(r.text, "html.parser")
                # Navigation/Footer entfernen – sonst Rauschen im Text
                for tag in soup(["nav", "footer", "header", "script", "style", "aside", "form"]):
                    tag.decompose()
                text = soup.get_text(" ")
                text = re.sub(r"\s+", " ", text)
                title = (
                    soup.title.string.strip()
                    if soup.title and soup.title.string
                    else url
                )
            return text, title

        except Exception as e:
            last_err = e
            continue

    return f"ERROR: {last_err}", "Fehler beim Laden"


# =============================================================================
# Treffer extrahieren – inkl. Überlappungs-Deduplizierung
# -----------------------------------------------------------------------------
# Hinweis: Die alte EXCLUDE-Liste (z. B. "Budget", "Euro", "Antragsteller")
# war zu aggressiv. Wenn eine echte Beschränkung im gleichen 240-Zeichen-Fenster
# wie "Budget" oder "Euro" stand, wurde sie verworfen. Entfernt.
# =============================================================================
def extract_quotes(text: str):
    results = []
    taken_spans = []  # Überlappungen vermeiden
    for pattern, label in PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE | re.DOTALL):
            span = (m.start(), m.end())
            if any(not (span[1] <= s[0] or span[0] >= s[1]) for s in taken_spans):
                continue
            taken_spans.append(span)
            snippet_start = max(0, m.start() - 120)
            snippet_end = min(len(text), m.end() + 120)
            snippet = text[snippet_start:snippet_end].strip()
            highlighted = re.sub(
                re.escape(m.group(0)),
                f">>>{m.group(0)}<<<",
                snippet,
                count=1,
                flags=re.IGNORECASE,
            )
            results.append(f"[{label}] {highlighted}")
    return "\n\n---\n\n".join(results)


# =============================================================================
# Streamlit UI
# =============================================================================
st.title("🔍 Förder-Screener")
st.caption(
    "Prüft Ausschreibungstexte auf Beschränkungen bei der Anzahl von "
    "Anträgen bzw. Skizzen pro Einrichtung."
)

urls = st.text_area("URLs (eine pro Zeile)", height=220)

if st.button("Start"):
    url_list = [u.strip() for u in urls.split("\n") if u.strip()]
    if not url_list:
        st.warning("Bitte mindestens eine URL eingeben.")
    else:
        progress = st.progress(0.0, text="Starte Analyse ...")
        results = []
        for i, url in enumerate(url_list, 1):
            progress.progress(i / len(url_list), text=f"Prüfe {i}/{len(url_list)}: {url[:80]}")
            text, title = get_content(url)
            if text.startswith("ERROR"):
                status = "Nicht prüfbar"
                quote = text
            else:
                quote = extract_quotes(text)
                status = "JA – TREFFER" if quote else "Keine Beschränkung gefunden"
            results.append({
                "Nr": i,
                "Titel": title,
                "URL": url,
                "Status": status,
                "Zitat": quote,
            })
        progress.empty()

        df = pd.DataFrame(results)
        st.dataframe(df, use_container_width=True)

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 CSV herunterladen",
            csv,
            "foerder_screening.csv",
            "text/csv",
        )
