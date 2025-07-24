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

CONTEXT_CHARS = 20  # antal tecken före och efter nyckelord


def extract_date(context):
    # Exkludera vanligt förekommande ord som inte är införandedatum
    if any(neg in context for neg in ["publicerad", "uppdaterad", "senast ändrad"]):
        return None

    # Prioritera datum som föregås av specifika uttryck
    pattern = re.compile(
        r"(från och med|införs|gäller från och med)?\s*(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        re.IGNORECASE
    )
    match = pattern.search(context)
    if match:
        return f"{match.group(2)} {match.group(3).lower()}"

    # Alternativt ISO-format
    match_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", context)
    if match_iso:
        try:
            date = datetime.strptime(match_iso.group(0), "%Y-%m-%d")
            return date.strftime("%-d %B")  # t.ex. 21 juli
        except:
            pass
    return None



def check_url(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.188"
    }
    try:
        # Steg 1: Hämta startsidan
        r = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")

        # Steg 2: Leta efter <a>-taggar med ordet "bevattningsförbud"
        a_tags = soup.find_all("a", string=re.compile(r"bevattningsförbud", re.IGNORECASE))
        news_url = None
        for a in a_tags:
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    news_url = href
                else:
                    news_url = url.rstrip("/") + href
                break  # Vi tar första träffen

        if news_url:
            print(f"🔗 Följer nyhetslänk: {news_url}")
            r = requests.get(news_url, headers=headers, timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")

        # Steg 3: Extrahera bara text från nyhetssidan
        main = soup.find("main") or soup.find("article") or soup
        text = main.get_text().lower()

        hits = extract_hits_with_context(text)
        print(f"🎯 Hittade {len(hits)} träff(ar) på bevattningsförbud i rätt artikel.")
        return hits

    except Exception as e:
        print(f"⚠️ Fel vid kontroll av {url}: {e}")
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

def extract_dates(context):
    matches = re.findall(r"\b(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)\b", context)
    iso_matches = re.findall(r"\b(20\d{2})-(\d{2})-(\d{2})\b", context)

    dates = []
    for day, month in matches:
        try:
            date = datetime.strptime(f"{day} {month}", "%d %B")
            date = date.replace(year=datetime.today().year)
            dates.append(date)
        except:
            continue

    for year, month, day in iso_matches:
        try:
            date = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
            dates.append(date)
        except:
            continue

    return dates


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
                # Försök extrahera datum från själva kontexten där nyckelordet hittades
                date = None
                for _, context in hits:
                    date = extract_date(context)
                    if date:
                        break  # Första meningsfulla datum nära nyckelordet

                if date:
                    alert_text = f"{kommun} har infört bevattningsförbud den {date}. Se länk för mer information: <a href='{url}'>{url}</a>"
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
