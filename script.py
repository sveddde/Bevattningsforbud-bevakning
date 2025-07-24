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
    "bevattningsförbud" or
                soup.find("article") or
                soup.find("section", class_="news") or
                soup.find("div", class_="news") or
                soup
]

CONTEXT_CHARS = 100  # antal tecken före och efter nyckelord


def extract_hits_with_context(text):
    results = []
    for keyword in KEYWORDS:
        for match in re.finditer(keyword, text):
            start = max(0, match.start() - CONTEXT_CHARS)
            end = min(len(text), match.end() + CONTEXT_CHARS)
            context = text[start:end].strip()

            # Hoppa över om kontexten innehåller "inget bevattningsförbud"
            if "inget bevattningsförbud" in context or "inga bevattningsförbud" in context:
                continue

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

        # Sök efter vanliga nyhets/aktuellt-sektioner
        sections = soup.find_all(["section", "div", "main", "article"])
        relevant_text = ""
        for s in sections:
            id_class = (s.get("id") or "") + " " + " ".join(s.get("class", []))
            if any(word in id_class.lower() for word in ["nyhet", "aktuellt", "news", "start", "senaste"]):
                relevant_text += s.get_text().lower() + "\n"

        # Om inget hittades, backa till main
        if not relevant_text:
            main = soup.find("main") or soup.find("article") or soup
            relevant_text = main.get_text().lower()

        hits = extract_hits_with_context(relevant_text)
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


import re
from datetime import datetime

def extract_date(context):
    # Försök hitta ett datum i formen 21 juli eller 2025-07-21
    match = re.search(r"\b(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)\b", context)
    if match:
        return f"{match.group(1)} {match.group(2)}"

    match_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", context)
    if match_iso:
        try:
            date = datetime.strptime(match_iso.group(0), "%Y-%m-%d")
            return date.strftime("%-d %B")  # t.ex. 21 juli
        except:
            pass
    return None

def main():
    alerts = []
    seen_kommuner = set()

    with open("kommuner.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kommun = row["kommun"]
            url = row["webbplats"]

            if kommun in seen_kommuner:
                continue
            seen_kommuner.add(kommun)

            hits = check_url(url)
            if hits:
                # Använd första datum vi hittar i någon av kontexterna
                first_date = None
                for _, context in hits:
                    first_date = extract_date(context)
                    if first_date:
                        break

                if first_date:
                    alert_text = f"{kommun} har infört bevattningsförbud den {first_date}. Se länk för mer information: <a href='{url}'>{url}</a>"
                else:
                    alert_text = f"{kommun} har infört bevattningsförbud. Se länk för mer information: <a href='{url}'>{url}</a>"

                alerts.append(alert_text)

    if alerts:
        body = "<br><br>".join(alerts)
        send_email(
            f"Bevattningsförbud upptäckt {datetime.today().date()}",
            body
        )

if __name__ == "__main__":
    main()
