import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber


# =============================================================================
# PATTERN-BAUSTEINE
# -----------------------------------------------------------------------------
# Aus Bausteinen zusammengesetzt, damit Erweiterungen nur an einer Stelle
# eingetragen werden müssen (z. B. neue Subjekt-Wörter oder Objekt-Wörter).
# =============================================================================
UML_A = r"(ä|ae)"
UML_O = r"(ö|oe)"
UML_U = r"(ü|ue)"

# Gültige Subjekte (worauf sich die Beschränkung bezieht)
SUBJ = (
    r"(Hochschule|Einrichtung|Institution|Universit" + UML_A + r"t|"
    r"antragstellende[rn]?\s+(Einrichtung|Hochschule|Institution)|"
    r"Antragsteller(in)?|Ausschreibung|Ausschreibungsrunde|"
    r"F" + UML_O + r"rderrunde|F" + UML_O + r"rderperiode|Runde|"
    r"Stichtag|Fakult" + UML_A + r"t|Standort)"
)

# Optionales Adjektiv (max. 3 Wörter) zwischen "Jede/Pro" und Substantiv.
# Wichtig, damit z. B. "Jede antragberechtigte Einrichtung" gematcht wird.
ADJ = r"(?:[\wäöüÄÖÜß\-]+\s+){0,3}?"

# Gültige Objekte (was beschränkt wird)
OBJ = (
    r"(Antrag|Antr" + UML_A + r"ge|Skizze|Skizzen|Projektskizze|Projektskizzen|"
    r"Projektbeteiligung|Vorhaben|Projekt|Projekte|Vorhabenbeschreibung|"
    r"Zuwendung|Absichtserkl" + UML_A + r"rung|Absichtserkl" + UML_A + r"rungen)"
)

# Mengen-Qualifier (inkl. Zahlwörter 1–3)
QTY = (
    r"(ein|eine|einen|1|zwei|2|drei|3|maximal|max\.|"
    r"h" + UML_O + r"chstens|nur|nicht mehr als|lediglich)"
)


# =============================================================================
# PATTERNS
# -----------------------------------------------------------------------------
# Änderungen gegenüber der vorherigen Version:
#   • Adjektive zwischen "Jede/Pro" und dem Substantiv werden jetzt erlaubt
#     (z. B. "Jede antragberechtigte Einrichtung ...").
#   • "Ausschreibung", "Runde", "Förderperiode" etc. sind jetzt gültige
#     Subjekte (z. B. "Pro Ausschreibung kann jede Universität einen Antrag
#     stellen.").
#   • Neues Pattern #4 für "X kann einen Antrag stellen/einreichen" ohne
#     explizites "nur"/"maximal" – deckt implizite Mengenangaben ab.
#   • Verben erweitert um Plural (können/dürfen).
#   • Objekte erweitert um "Absichtserklärung".
# =============================================================================
PATTERNS = [
    # 1. "pro/je <opt. Adj> Einrichtung ... <Qty> ... Antrag"
    (
        r"\b(pro|je)\s+" + ADJ + r"\b" + SUBJ + r"\b"
        r".{0,80}?\b" + QTY + r"\b"
        r".{0,40}?\b" + OBJ + r"\b",
        "pro/je Einrichtung"
    ),

    # 2. "(nur|maximal|...) ein/eine/X ... Antrag/Skizze"
    (
        r"\b(nur|maximal|max\.|h" + UML_O + r"chstens|nicht mehr als|lediglich)\b"
        r".{0,60}?\b(ein|eine|einen|1|zwei|2|drei|3)\b"
        r".{0,20}?\b" + OBJ + r"\b",
        "Mengenbegrenzung"
    ),

    # 3. "Eine/Jede/Pro <opt. Adj> X (darf|kann|...) ... (nur|maximal|...) ... Antrag"
    (
        r"\b(Eine|Jede[rs]?|Je|Pro)\s+" + ADJ + r"\b" + SUBJ + r"\b"
        r".{0,60}?\b(darf|kann|soll|wird|k" + UML_O + r"nnen|d" + UML_U + r"rfen)\b"
        r".{0,80}?\b(nicht mehr als|maximal|max\.|nur|h" + UML_O + r"chstens)\b"
        r".{0,40}?\b(ein|eine|einen|1|zwei|2|drei|3)\b"
        r".{0,40}?\b" + OBJ,
        "Einrichtung darf nur"
    ),

    # 4. "Pro/Je X (kann|darf) ... einen Antrag stellen/einreichen"
    #    Deckt implizite Mengenangaben ab (ohne explizites "nur").
    (
        r"\b(Pro|Je|Jede[rs]?)\s+" + ADJ + r"\b" + SUBJ + r"\b"
        r".{0,120}?\b(kann|darf|soll|k" + UML_O + r"nnen|d" + UML_U + r"rfen)\b"
        r".{0,80}?\b(ein|eine|einen|1)\s+" + OBJ + r"\b"
        r".{0,40}?\b(stellen|einreichen|ein.?reichen|beantragen|vorlegen|abgeben)\b",
        "X kann einen Antrag stellen"
    ),

    # 5. Mehrfachantragstellung nicht zulässig
    (
        r"\b(Mehrfachantrag|Mehrfachantragstellung|Mehrfacheinreichung|"
        r"mehrere\s+Antr" + UML_A + r"ge|mehrere\s+Skizzen|"
        r"mehr als eine\s+(Skizze|Antrag))\b"
        r".{0,80}?\b(nicht|aus(-?\s*)?geschlossen|unzul" + UML_A + r"ssig|"
        r"nicht zul" + UML_A + r"ssig|nicht m" + UML_O + r"glich|"
        r"nicht gestattet|ausgeschlossen)\b",
        "Mehrfachantragstellung"
    ),

    # 6. "beschränkt/begrenzt auf X Anträge/Skizzen"
    (
        r"\b(beschr" + UML_A + r"nkt|begrenzt|Begrenzung|Beschr" + UML_A + r"nkung)\b"
        r".{0,40}?\bauf\s+(ein|eine|1|zwei|2|drei|3|maximal)\b"
        r".{0,40}?\b" + OBJ + r"\b",
        "Begrenzung auf Anzahl"
    ),

    # 7. Hochschulinterne Vorauswahl (mit Wortgrenzen!)
    (
        r"\b(hochschulintern|institutionsintern|universit" + UML_A + r"tsintern)"
        r"(e|er|es|en)?\b"
        r".{0,40}?\b(Vorauswahl|Auswahlverfahren|Priorisierung|Abstimmung)\b",
        "Interne Vorauswahl"
    ),

    # 8. Plural: Einrichtungen/Hochschulen können/dürfen nicht mehr als...
    (
        r"\b(Einrichtungen|Hochschulen|Universit" + UML_A + r"ten)\b"
        r".{0,40}?\b(k" + UML_O + r"nnen|d" + UML_U + r"rfen)\b"
        r".{0,60}?\b(nicht mehr als|maximal|max\.|nur|h" + UML_O + r"chstens)\b"
        r".{0,40}?\b(ein|eine|einen|1|zwei|2|drei|3)\b"
        r".{0,40}?\b" + OBJ,
        "Plural Einrichtungen"
    ),

    # 9. Englisch: one proposal per institution
    (
        r"\b(only one|maximum of one|at most one|one)\b\s+"
        r"(proposal|application|submission)\b"
        r".{0,40}?\b(per|by each)\s+"
        r"(institution|university|applicant|organisation|organization)\b",
        "EN: one per institution"
    ),
    (
        r"\b(multiple|more than one)\b\s+"
        r"(proposals|applications|submissions)\b"
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
# =============================================================================
def is_pdf_content(response) -> bool:
    ct = response.headers.get("content-type", "").lower()
    if "pdf" in ct:
        return True
    return response.content[:4] == b"%PDF"


def clean_pdf_text(text: str) -> str:
    """Silbentrennung auflösen, Whitespace normalisieren, CID-Probleme kennzeichnen."""
    cid_count = len(re.findall(r"\(cid:\d+\)", text))
    total_len = max(len(text), 1)
    if cid_count > 20 and (cid_count * 8) / total_len > 0.05:
        text = (
            "[⚠️ HINWEIS: Dieses PDF verwendet CID-kodierte Fonts. "
            "Textextraktion nur eingeschränkt möglich – bitte manuell prüfen.] "
            + text
        )
    text = re.sub(r"-\s*\n\s*", "", text)
    text = re.sub(r"\s+", " ", text)
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
                title = " ".join(text.split()[:10])[:100] or "PDF ohne Titel"
            else:
                soup = BeautifulSoup(r.text, "html.parser")
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
# Treffer extrahieren – mit Überlappungs-Deduplizierung
# =============================================================================
def extract_quotes(text: str):
    results = []
    taken_spans = []
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
            progress.progress(
                i / len(url_list),
                text=f"Prüfe {i}/{len(url_list)}: {url[:80]}"
            )
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
