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
    "bevattningsförbud"
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
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.188"
    }
    try:
        r = requests.get(url, headers=headers, timeout=35)
        soup = BeautifulSoup(r.text, "html.parser")

        # Prioritera nyhets-/aktuellt-sektioner
        main = (soup.find("main") or
                soup.find("article") or
                soup.find("section", class_="news") or
                soup.find("div", class_="news") or
                soup)

        text = main.get_text(separator=" ").lower()

       hits = extract_hits_with_context(text)

        print(f"DEBUG: Hits för URL {url}: {len(hits)} träff(ar)")
        for keyword, context in hits:
            print(f"  Keyword: {keyword}")
            print(f"  Context: {context}")

        # Om inga träffar, skriv ut början av texten för felsökning
        if not hits:
            print(f"DEBUG: Ingen träff i texten (början av texten): {text[:300]}...")

        return hits
    except Exception as e:
        print(f"Fel vid kontroll av {url}: {e}")
        return []


def send_email(subject, body):
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
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
    print(f"DEBUG: Hits for {kommun}:")
    for keyword, context in hits:
        print(f"  Keyword: '{keyword}'")
        print(f"  Context: '{context}'")
    summary = "<ul>"
    for _, context in hits:
        safe_context = context.replace("\n", " ").replace("<", "&lt;").replace(">", "&gt;")
        summary += f"<li>...{safe_context}...</li>"
    summary += "</ul>"

    alerts.append(
        f"<b>{kommun}</b>: <a href='{url}'>{url}</a><br>{summary}"
    )

    if alerts:
        body = "<br><br>".join(alerts)
        send_email(
            f"Bevattningsförbud upptäckt {datetime.today().date()}",
            body
        )
    else:
        # Skicka debugmail om inga träffar alls hittades (kan tas bort senare)
        send_email(
            f"Bevattningsförbud BEVAKNING - inga träffar {datetime.today().date()}",
            "Ingen bevattningsförbuds-text hittades på någon kommunwebbplats idag."
        )


if __name__ == "__main__":
    main()
