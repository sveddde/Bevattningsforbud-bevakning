import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import os

# ---- Inställningar ---- #
GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS")
TO_EMAIL = os.getenv("TO_EMAIL", GMAIL_USER)

KEYWORDS = [
    "bevattningsförbud",
    "Bevattningsförbud",
    "införs bevattningsförbud",
    "bevattningsförbudet gäller tillsvidare",
    "bevattningsförbud införs",
    "Bevattningsförbud införs",
    "gäller bevattningsförbud",
    "har infört bevattningsförbud",
    "bevattningsförbud gäller"
]

NEGATIVE_PHRASES = [
    "upphävt",
    "upphört",
    "inte längre",
    "hävt",
    "hävs",
    "slutat gälla",
    "Bevattningsförbud upphävt"
]

# ---- Läs in kommunlistan ---- #
kommun_df = pd.read_csv("kommuner.csv")
kommun_urls = dict(zip(kommun_df["Kommun"], kommun_df["URL"]))

# ---- Caching + Parallell hämtning ---- #
@lru_cache(maxsize=128)
def fetch_url(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"Kunde inte hämta {url}: {e}")
        return ""

def fetch_pages_parallel(urls, max_workers=48):
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(fetch_url, url): url for url in urls}
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                html = future.result()
                results[url] = html
            except Exception as e:
                print(f"Fel vid hämtning av {url}: {e}")
    return results

# ---- Datumextraktion ---- #
def extract_hits_with_context(text):
    matches = []
    for keyword in KEYWORDS:
        for match in re.finditer(re.escape(keyword), text, re.IGNORECASE):
            start = max(match.start() - 80, 0)
            end = min(match.end() + 80, len(text))
            context = text[start:end]
            if not any(neg in context for neg in NEGATIVE_PHRASES):
                matches.append(context)
    return matches

def extract_date(text):
    # Leta efter mönster som "1 augusti", "den 3 juli" etc.
    match = re.search(r"(?:den )?(\d{1,2}) (januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)", text, re.IGNORECASE)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return ""

# ---- Mailfunktion ---- #
def send_email(message_body):
    subject = f"Bevattningsförbud upptäckt {datetime.today().date()}"
    msg = MIMEText(message_body, "html")
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg["Subject"] = subject

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASS)
            smtp.send_message(msg)
            print("Mail skickat.")
    except Exception as e:
        print(f"Kunde inte skicka mail: {e}")

# ---- Huvudlogik ---- #
html_pages = fetch_pages_parallel(list(kommun_urls.values()))

mail_hits = []
for kommunnamn, url in kommun_urls.items():
    html = html_pages.get(url, "")
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ")
    matches = extract_hits_with_context(text)
    if matches:
        for m in matches:
            datum = extract_date(m)
            datumtext = f"den {datum}" if datum else ""
            mail_hits.append(f"{kommunnamn} har infört bevattningsförbud {datumtext}. Se länk för mer information: <a href='{url}'>{url}</a>")

if mail_hits:
    mail_body = "<br><br>".join(mail_hits)
    send_email(mail_body)
