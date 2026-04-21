import streamlit as st
import requests
import re
import pandas as pd
from bs4 import BeautifulSoup
from io import BytesIO
import pdfplumber


# =============================================================================
# Streamlit Page Config – muss als allererste Streamlit-Anweisung stehen.
# =============================================================================
st.set_page_config(
    page_title="Förder-Screener · Universität zu Köln",
    page_icon="📋",  # Alternative zum Lupen-Emoji
    layout="wide",
)


# =============================================================================
# Universität zu Köln – Corporate Design (Markenhandbuch Juli 2023)
# -----------------------------------------------------------------------------
# Primäre Farben:
#   Universitätsblau   #005176
#   Türkis             #009dcc
#   Korall             #ea564f
# Hausschrift: Albert Sans (Google Font, Fallback: System-Sans-Serif)
# =============================================================================
UZK_BLAU = "#005176"
UZK_TUERKIS = "#009dcc"
UZK_KORALL = "#ea564f"
UZK_HELLGRAU = "#f4f6f8"
UZK_DUNKELGRAU = "#1a1a1a"

UZK_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Albert+Sans:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {{
    font-family: 'Albert Sans', -apple-system, BlinkMacSystemFont,
                 'Segoe UI', sans-serif !important;
}}

/* Hauptüberschrift: Versalien-Stil nach Uni-Köln-Markenhandbuch */
.uzk-header {{
    border-left: 6px solid {UZK_KORALL};
    padding: 0.5rem 0 0.5rem 1.2rem;
    margin: 0.5rem 0 1.5rem 0;
}}
.uzk-header h1 {{
    font-family: 'Albert Sans', sans-serif !important;
    font-weight: 600 !important;
    color: {UZK_BLAU} !important;
    font-size: 2.4rem !important;
    letter-spacing: 0.02em !important;
    text-transform: uppercase !important;
    margin: 0 !important;
    padding: 0 !important;
    line-height: 1.1 !important;
}}
.uzk-header .subtitle {{
    color: {UZK_DUNKELGRAU};
    font-size: 0.95rem;
    margin-top: 0.4rem;
    opacity: 0.8;
}}
.uzk-footer-line {{
    color: #777;
    font-size: 0.8rem;
    margin-top: 2rem;
    padding-top: 1rem;
    border-top: 1px solid #e0e0e0;
}}

/* Primärbutton in Universitätsblau */
.stButton > button[kind="primary"] {{
    background-color: {UZK_BLAU} !important;
    border-color: {UZK_BLAU} !important;
    color: white !important;
    font-family: 'Albert Sans', sans-serif !important;
    font-weight: 500 !important;
}}
.stButton > button[kind="primary"]:hover {{
    background-color: {UZK_TUERKIS} !important;
    border-color: {UZK_TUERKIS} !important;
}}

/* Download-Button dezenter */
.stDownloadButton > button {{
    background-color: white !important;
    color: {UZK_BLAU} !important;
    border: 1px solid {UZK_BLAU} !important;
}}
.stDownloadButton > button:hover {{
    background-color: {UZK_BLAU} !important;
    color: white !important;
}}

/* Textarea: dezenter Fokusrahmen in Uni-Blau */
textarea:focus {{
    border-color: {UZK_BLAU} !important;
    box-shadow: 0 0 0 1px {UZK_BLAU} !important;
}}

/* Progressbar in Uni-Blau */
.stProgress > div > div > div > div {{
    background-color: {UZK_BLAU} !important;
}}

/* Metric-Karten in Uni-Köln-Farben */
[data-testid="stMetric"] {{
    background: {UZK_HELLGRAU};
    padding: 1rem 1.2rem;
    border-radius: 4px;
    border-left: 4px solid {UZK_BLAU};
}}
[data-testid="stMetricValue"] {{
    color: {UZK_BLAU} !important;
    font-weight: 600 !important;
}}

/* Links in Uni-Türkis */
a {{
    color: {UZK_TUERKIS} !important;
}}
a:hover {{
    color: {UZK_BLAU} !important;
}}
</style>
"""


# =============================================================================
# PATTERNS (unverändert gegenüber v5)
# =============================================================================
UML_A = r"(ä|ae)"
UML_O = r"(ö|oe)"
UML_U = r"(ü|ue)"

SUBJ = (
    r"(Hochschule|Einrichtung|Institution|Universit" + UML_A + r"t|"
    r"antragstellende[rn]?\s+(Einrichtung|Hochschule|Institution)|"
    r"Antragsteller(in)?|Ausschreibung|Ausschreibungsrunde|"
    r"F" + UML_O + r"rderrunde|F" + UML_O + r"rderperiode|Runde|"
    r"Stichtag|Fakult" + UML_A + r"t|Standort)"
)
ADJ = r"(?:[\wäöüÄÖÜß\-]+\s+){0,3}?"
OBJ = (
    r"(Antrag|Antr" + UML_A + r"ge|Skizze|Skizzen|Projektskizze|Projektskizzen|"
    r"Projektbeteiligung|Vorhaben|Projekt|Projekte|Vorhabenbeschreibung|"
    r"Zuwendung|Absichtserkl" + UML_A + r"rung|Absichtserkl" + UML_A + r"rungen|"
    r"Verbundkoordination|Koordination)"
)
NUM = r"(ein|eine|einen|einem|einer|1|zwei|2|drei|3)"
QTY = (
    r"(" + NUM + r"|maximal|max\.|h" + UML_O + r"chstens|nur|"
    r"nicht mehr als|lediglich)"
)
MONEY_BLOCKLIST = (
    r"(Million|Mio\.?|Mrd\.?|Milliard|Euro|EUR|€|Tausend|T€|TEUR|"
    r"Prozent|%|Stunden|Monate|Jahre)"
)
ABBREV = r"(?:bzw|ggf|vgl|etc|usw|ca|Nr|Abs|d\.\s*h|z\.\s*B|u\.\s*a|bspw|max|min|Mio|Mrd)"
SAFE_CHAR = r"(?:[^.]|" + ABBREV + r"\.)"

PATTERNS = [
    (r"\b(pro|je)\s+" + ADJ + r"\b" + SUBJ + r"\b"
     r".{0,80}?\b" + QTY + r"\b.{0,40}?\b" + OBJ + r"\b",
     "pro/je Einrichtung"),
    (r"\b(nur|maximal|max\.|h" + UML_O + r"chstens|nicht mehr als|lediglich)\b"
     r".{0,60}?\b" + NUM + r"\b"
     r"(?!\s+" + MONEY_BLOCKLIST + r")"
     r".{0,20}?\b" + OBJ + r"\b",
     "Mengenbegrenzung"),
    (r"\b(Eine|Jede[rs]?|Je|Pro)\s+" + ADJ + r"\b" + SUBJ + r"\b"
     r".{0,60}?\b(darf|kann|soll|wird|k" + UML_O + r"nnen|d" + UML_U + r"rfen)\b"
     r".{0,80}?\b(nicht mehr als|maximal|max\.|nur|h" + UML_O + r"chstens)\b"
     r".{0,40}?\b" + NUM + r"\b.{0,40}?\b" + OBJ,
     "Einrichtung darf nur"),
    (r"\b(Eine|Pro|Je|Jede[rs]?)\s+" + ADJ + r"\b" + SUBJ + r"\b"
     r".{0,120}?\b(kann|darf|soll|k" + UML_O + r"nnen|d" + UML_U + r"rfen)\b"
     r".{0,80}?\b(ein|eine|einen|einem|einer|1)\s+" + OBJ + r"\b"
     + SAFE_CHAR + r"{0,200}?\b(stellen|einreichen|ein.?reichen|beantragen|"
     r"vorlegen|abgeben|" + UML_U + r"bernehmen)\b",
     "X kann einen stellen"),
    (r"\b(Mehrfachantrag|Mehrfachantragstellung|Mehrfacheinreichung|"
     r"mehrere\s+Antr" + UML_A + r"ge|mehrere\s+Skizzen|"
     r"mehr als eine\s+(Skizze|Antrag))\b"
     r".{0,80}?\b(nicht|aus(-?\s*)?geschlossen|unzul" + UML_A + r"ssig|"
     r"nicht zul" + UML_A + r"ssig|nicht m" + UML_O + r"glich|"
     r"nicht gestattet|ausgeschlossen)\b",
     "Mehrfachantragstellung"),
    (r"\b(beschr" + UML_A + r"nkt|begrenzt|Begrenzung|Beschr" + UML_A + r"nkung)\b"
     r".{0,40}?\bauf\s+" + NUM + r"\b.{0,40}?\b" + OBJ + r"\b",
     "Begrenzung auf Anzahl"),
    (r"\b(hochschulintern|institutionsintern|universit" + UML_A + r"tsintern)"
     r"(e|er|es|en)?\b"
     r".{0,40}?\b(Vorauswahl|Auswahlverfahren|Priorisierung|Abstimmung)\b",
     "Interne Vorauswahl"),
    (r"\b(Einrichtungen|Hochschulen|Universit" + UML_A + r"ten)\b"
     r".{0,40}?\b(k" + UML_O + r"nnen|d" + UML_U + r"rfen)\b"
     r".{0,60}?\b(nicht mehr als|maximal|max\.|nur|h" + UML_O + r"chstens)\b"
     r".{0,40}?\b" + NUM + r"\b.{0,40}?\b" + OBJ,
     "Plural Einrichtungen"),
    (r"\b(only one|maximum of one|at most one|one)\b\s+"
     r"(proposal|application|submission)\b"
     r".{0,40}?\b(per|by each)\s+"
     r"(institution|university|applicant|organisation|organization)\b",
     "EN: one per institution"),
    (r"\b(multiple|more than one)\b\s+(proposals|applications|submissions)\b"
     r".{0,40}?\b(not allowed|not permitted|excluded|prohibited)\b",
     "EN: multiple not allowed"),
]


# =============================================================================
# Titel-Extraktion
# -----------------------------------------------------------------------------
# Ersetzt die alte Logik "nimm <title> oder URL". Sucht stattdessen nach
# aussagekräftigen Titeln (H1/H2, OG-Meta, Schlüsselwörter wie
# "Bekanntmachung", "Richtlinie zur Förderung", "Förderaufruf") und fällt bei
# Misserfolg auf eine Domain-Bezeichnung zurück.
# =============================================================================
def _clean_title(title, max_len=130):
    if not title:
        return ""
    t = re.sub(r"\s+", " ", title).strip()
    # Typografische Anführungszeichen normalisieren
    t = t.replace("„", '"').replace("“", '"').replace("”", '"')
    if len(t) > max_len:
        t = t[:max_len].rsplit(" ", 1)[0] + "…"
    return t


def _is_bad_title(t):
    """Erkennt offensichtlich untaugliche Titel-Kandidaten."""
    if not t or len(t.strip()) < 5:
        return True
    t = t.strip()
    if t.startswith(("http://", "https://", "www.")):
        return True
    if t.lower() in {"pdf ohne titel", "index", "startseite", "home", "dokument"}:
        return True
    if re.match(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$", t):
        return True
    return False


def extract_html_title(soup, url):
    """Versucht in dieser Reihenfolge: H1 (ggf. ergänzt durch Folge-Element),
    OG-Meta-Title, <title>, Domain-Fallback."""
    # 1. H1
    h1 = soup.find("h1")
    if h1:
        h1_text = h1.get_text(" ", strip=True)
        if not _is_bad_title(h1_text):
            # Wenn H1 nur "Bekanntmachung" o. Ä. enthält, ergänze das Folge-Element
            if h1_text.lower().strip() in ("bekanntmachung", "förderaufruf",
                                            "richtlinie", "merkblatt"):
                nxt = h1.find_next(["h2", "p", "strong", "div"])
                if nxt:
                    nxt_text = nxt.get_text(" ", strip=True)
                    if nxt_text and 10 < len(nxt_text) < 250:
                        return _clean_title(f"{h1_text}: {nxt_text}")
            return _clean_title(h1_text)

    # 2. OG-Title
    og = soup.find("meta", property="og:title")
    if og and og.get("content") and not _is_bad_title(og["content"]):
        return _clean_title(og["content"])

    # 3. <title>
    if soup.title and soup.title.string:
        t = soup.title.string.strip()
        if not _is_bad_title(t):
            return _clean_title(t)

    # 4. Erstes H2
    h2 = soup.find("h2")
    if h2:
        h2_text = h2.get_text(" ", strip=True)
        if not _is_bad_title(h2_text):
            return _clean_title(h2_text)

    # 5. Domain-Fallback
    m = re.match(r"https?://(?:www\.|www\d+\.)?([^/]+)", url)
    domain = m.group(1) if m else url
    return f"[Seite auf {domain}]"


def extract_pdf_title(text, max_search_chars=2500):
    """Sucht in den ersten ~2500 Zeichen nach einem aussagekräftigen Titel.
    Erkennt gängige Strukturen: 'Bekanntmachung' + Folgezeile, 'Richtlinie
    zur Förderung', 'Förderaufruf', 'Förderrichtlinie' etc."""
    head = text[:max_search_chars]
    lines = [ln.strip() for ln in re.split(r"[\n\r]+", head) if ln.strip()]

    # 1. Standalone-Keyword gefolgt von Titelzeile
    for i, line in enumerate(lines[:40]):
        if re.match(
            r"^(bekanntmachung|f" + UML_O + r"rderaufruf|f" + UML_O + r"rderrichtlinie|merkblatt)\s*$",
            line, re.IGNORECASE
        ):
            following = []
            for j in range(i + 1, min(i + 5, len(lines))):
                nxt = lines[j]
                # Bei Datum oder Gliederungsnummer abbrechen
                if re.match(r"^(vom\s+\d|\d+\.\s+[A-ZÄÖÜ]|\d{1,2}\.\d{1,2}\.\d{2,4}$)",
                            nxt, re.IGNORECASE):
                    break
                if len(nxt) > 3 and not nxt.startswith("www"):
                    following.append(nxt)
                if len(following) >= 2 and len(" ".join(following)) > 40:
                    break
            if following:
                return _clean_title(f"{line}: {' '.join(following)}")

    # 2. Zeilen mit expliziten Förder-Schlüsselwörtern
    for line in lines[:40]:
        if re.search(
            r"(Richtlinie zur F" + UML_O + r"rderung|F" + UML_O + r"rderrichtlinie|"
            r"F" + UML_O + r"rderaufruf|Programminformation|"
            r"Bekanntmachung\s+(der|des|der Richtlinie|zur|über))",
            line, re.IGNORECASE
        ):
            if len(line) > 25:
                return _clean_title(line)

    # 3. Erste "substanzielle" Zeile, die keine Behörden-Kopfzeile oder Adresse ist
    BOILERPLATE = re.compile(
        r"^(Bundesministerium|Ministerium für|Landesministerium|Seite \d|"
        r"www\.|Tel\.|\d{5}\s|Stand:|Version\s|Anlage)",
        re.IGNORECASE
    )
    for line in lines[:40]:
        if BOILERPLATE.match(line):
            continue
        if len(line) < 20 or len(line) > 250:
            continue
        if re.match(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$", line):
            continue
        return _clean_title(line)

    # 4. Absoluter Fallback
    return _clean_title(" ".join(lines[:3]) if lines else "PDF ohne erkennbaren Titel")


# =============================================================================
# URL-Transformation, PDF-Erkennung, Cleanup
# =============================================================================
def transform_url(url: str) -> str:
    if "bmftr.bund.de/SharedDocs/Bekanntmachungen" in url:
        return url.split("?")[0] + "?view=renderNewsletterHtml"
    return url


def is_pdf_content(response) -> bool:
    ct = response.headers.get("content-type", "").lower()
    if "pdf" in ct:
        return True
    return response.content[:4] == b"%PDF"


def clean_pdf_text(text: str) -> str:
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
# Content-Fetch
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
    for _ in range(retries + 1):
        try:
            r = requests.get(url_fetch, timeout=30, headers=headers, allow_redirects=True)
            r.raise_for_status()

            if is_pdf_content(r):
                with pdfplumber.open(BytesIO(r.content)) as pdf:
                    text = "\n".join((p.extract_text() or "") for p in pdf.pages)
                # Titel VOR dem Whitespace-Kollaps extrahieren (Zeilenumbrüche hilfreich)
                raw_text_for_title = text
                text = clean_pdf_text(text)
                title = extract_pdf_title(raw_text_for_title)
            else:
                soup = BeautifulSoup(r.text, "html.parser")
                # WICHTIG: Titel-Extraktion VOR dem Entfernen der Struktur-Tags
                title = extract_html_title(soup, url)
                for tag in soup(["nav", "footer", "header", "script", "style", "aside", "form"]):
                    tag.decompose()
                text = soup.get_text(" ")
                text = re.sub(r"\s+", " ", text)
            return text, title

        except Exception as e:
            last_err = e
            continue

    return f"ERROR: {last_err}", "Fehler beim Laden"


# =============================================================================
# Treffer extrahieren
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
st.markdown(UZK_CSS, unsafe_allow_html=True)

st.markdown(
    f"""
<div class="uzk-header">
  <h1>Förder-Screener</h1>
  <div class="subtitle">Prüft Ausschreibungstexte auf Beschränkungen bei der Anzahl von Anträgen bzw. Skizzen pro Einrichtung.</div>
</div>
""",
    unsafe_allow_html=True,
)

with st.container():
    urls = st.text_area(
        "URLs (eine pro Zeile)",
        height=280,
        placeholder="https://www.beispiel.de/foerderausschreibung-1\nhttps://www.beispiel.de/foerderausschreibung-2\n…",
    )

start_clicked = st.button("Analyse starten", type="primary")

if start_clicked:
    url_list = [u.strip() for u in urls.split("\n") if u.strip()]
    if not url_list:
        st.warning("Bitte mindestens eine URL eingeben.")
    else:
        progress = st.progress(0.0, text="Starte Analyse …")
        results = []
        for i, url in enumerate(url_list, 1):
            progress.progress(
                i / len(url_list),
                text=f"Prüfe {i}/{len(url_list)}: {url[:80]}",
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

        # KPI-Zeile in Uni-Köln-Farben
        n_total = len(df)
        n_hits = int((df["Status"] == "JA – TREFFER").sum())
        n_none = int((df["Status"] == "Keine Beschränkung gefunden").sum())
        n_err = int((df["Status"] == "Nicht prüfbar").sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Geprüfte URLs", n_total)
        c2.metric("Treffer", n_hits)
        c3.metric("Keine Beschränkung", n_none)
        c4.metric("Nicht prüfbar", n_err)

        st.subheader("Ergebnisübersicht")
        st.dataframe(
            df,
            width="stretch",
            height=min(650, 80 + len(df) * 90),
            column_config={
                "Nr": st.column_config.NumberColumn("Nr", width="small"),
                "Titel": st.column_config.TextColumn("Titel", width="large"),
                "URL": st.column_config.LinkColumn("URL", width="medium"),
                "Status": st.column_config.TextColumn("Status", width="small"),
                "Zitat": st.column_config.TextColumn("Zitat", width="large"),
            },
            hide_index=True,
        )

        # Detailansicht als Expander
        with st.expander("📋 Detailansicht pro URL (mit vollständigem Zitat)",
                         expanded=False):
            for _, row in df.iterrows():
                if row["Status"] == "JA – TREFFER":
                    icon = "✅"
                elif row["Status"] == "Nicht prüfbar":
                    icon = "⚠️"
                else:
                    icon = "➖"
                st.markdown(f"**{icon} Nr. {row['Nr']} – {row['Status']}**")
                st.markdown(f"🔗 [{row['URL']}]({row['URL']})")
                if row["Titel"]:
                    st.caption(f"Titel: {row['Titel']}")
                if row["Zitat"]:
                    st.text(row["Zitat"])
                st.divider()

        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "📥 CSV herunterladen",
            csv,
            "foerder_screening.csv",
            "text/csv",
        )

# Abbinder
st.markdown(
    '<div class="uzk-footer-line">Universität zu Köln · Dezernat 7 Forschungsmanagement</div>',
    unsafe_allow_html=True,
)
