# === script.py ===
import csv
import os
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import re

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS")
TO_EMAIL = os.getenv("TO_EMAIL", GMAIL_USER)

KEYWORDS = [
    "bevattningsförbud",
    "vattenförbud",
    "vattningsförbud",
    "torka",
    "begränsning"
]

CONTEXT_CHARS = 100  # antal tecken före och efter nyckelord


def extract_hits_with_context(text):
    results = []
    for keyword in KEYWORDS:
        for match in re.finditer(keyword, text):
            start = max(0, match.start() - CONTEXT_CHARS)
            end = min(len(text), match.end() + CONTEXT_CHARS)
            context = text[start:end].strip()
            results.append((keyword, context))
    return results


def check_url(url):
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")

        # Försök att bara ta med <main> eller artikeldelar först
        main = soup.find("main") or soup.find("article") or soup
        text = main.get_text().lower()

        hits = extract_hits_with_context(text)
        return hits
    except Exception as e:
        print(f"Fel vid kontroll av {url}: {e}")
        return []


def send_email(subject, body):
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER  # här kan du byta namn på variabeln till t.ex. EMAIL_USER om du vill
    msg["To"] = TO_EMAIL
    with smtplib.SMTP("smtp.office365.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        smtp.send_message(msg)


def main():
    alerts = []
    with open("kommuner.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kommun = row["kommun"]
            url = row["webbplats"]
            hits = check_url(url)
            if hits:
                summary = "<br>".join(
                    f"...{context}..." for _, context in hits
                )
                alerts.append(
                    f"<b>{kommun}</b>: <a href='{url}'>{url}</a><br><i>{summary}</i>"
                )

    if alerts:
        body = "<br><br>".join(alerts)
        send_email(
            f"Bevattningsförbud upptäckt {datetime.today().date()}",
            body
        )


if __name__ == "__main__":
    main()
