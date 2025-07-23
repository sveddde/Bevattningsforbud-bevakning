import csv
import os
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS")
TO_EMAIL = os.getenv("TO_EMAIL", GMAIL_USER)

KEYWORDS = ["bevattningsförbud", "vattenförbud", "vattningsförbud", "torka", "begränsning"]

def check_url(url):
    try:
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text().lower()
        return any(word in text for word in KEYWORDS)
    except Exception as e:
        print(f"Fel vid kontroll av {url}: {e}")
        return False

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
            k = row["kommun"]
            url = row["webbplats"]
            if check_url(url):
                alerts.append(f"<b>{k}</b>: <a href='{url}'>{url}</a>")

    if alerts:
        body = "<br>".join(alerts)
        send_email(f"Bevattningsförbud upptäckt {datetime.today().date()}", body)

if __name__ == "__main__":
    main()
