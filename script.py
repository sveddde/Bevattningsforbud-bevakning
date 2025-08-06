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

KEYWORD = "bevattningsförbud"

def extract_date(text):
    # Försök hitta datum i format "22 juli" eller "från och med 22 juli"
    patterns = [
        r"från och med (\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        r"(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        r"(\d{4}-\d{2}-\d{2})"
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            if len(match.groups()) == 2:
                dag = int(match.group(1))
                manad = match.group(2).lower()
                return f"{dag} {manad}"
            else:
                try:
                    dt = datetime.strptime(match.group(1), "%Y-%m-%d")
                    return dt.strftime("%-d %B").lower()
                except:
                    pass
    return None

def check_url(url):
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(separator="\n").lower()
        if KEYWORD in text:
            date = extract_date(text)
            return True, date, url
    except Exception as e:
        print(f"Fel vid hämtning av {url}: {e}")
    return False, None, url

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
            has_forbud, date, actual_url = check_url(url)
            if has_forbud:
                if date:
                    alerts.append(f"{kommun} har infört bevattningsförbud den {date}. Se mer: <a href='{actual_url}'>{actual_url}</a>")
                else:
                    alerts.append(f"{kommun} har infört bevattningsförbud. Se mer: <a href='{actual_url}'>{actual_url}</a>")
    if alerts:
        body = "<br><br>".join(alerts)
        send_email(f"Bevattningsförbud upptäckt {datetime.today().date()}", body)

if __name__ == "__main__":
    main()
