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
    "införs bevattningsförbud",
    "bevattningsförbudet gäller tillsvidare",
    "bevattningsförbud införs",
    "gäller bevattningsförbud",
    "har infört bevattningsförbud",
    "bevattningsförbud gäller"
]
NEGATIVE_PHRASES = [
    "inget bevattningsförbud",
    "inga bevattningsförbud",
    "upphävt bevattningsförbud",
    "bevattningsförbudet upphävs",
    "upphävts",
    "upphävdes",
    "har upphävts",
    "har tagits bort",
    "hävs",
    "är inte längre aktuellt"
]
SKIP_PHRASES = [
    "publicerad", "uppdaterad", "kalkning", "senast ändrad"
]

def extract_hits_with_context(text):
    results = []
    lines = text.split("\n")

    for line in lines:
        line_clean = line.strip()
        line_lower = line_clean.lower()

        if not line_clean:
            continue

        # Skippa irrelevanta rader
        if any(bad in line_lower for bad in SKIP_PHRASES):
            continue

        # Skippa rader där både negativt och positivt nämns
        if any(bad in line_lower for bad in NEGATIVE_PHRASES) and any(keyword in line_lower for keyword in KEYWORDS):
            continue

        # Matcha positiv fras utan negativ fras
        if any(keyword in line_lower for keyword in KEYWORDS):
            results.append(("bevattningsförbud", line_clean))

    return results

def extract_date(text):
    text = text.lower()

    pattern1 = re.compile(
        r"från och med (\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        re.IGNORECASE
    )
    match = pattern1.search(text)
    if match:
        return f"{match.group(1)} {match.group(2).lower()}"

    pattern2 = re.compile(
        r"(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        re.IGNORECASE
    )
    match = pattern2.search(text)
    if match:
        return f"{match.group(1)} {match.group(2).lower()}"

    match_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if match_iso:
        try:
            date = datetime.strptime(match_iso.group(0), "%Y-%m-%d")
            return date.strftime("%-d %B").lower()
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
        r = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")

        a_tags = soup.find_all("a", string=re.compile(r"bevattningsförbud", re.IGNORECASE))

        for a in a_tags:
            href = a.get("href")
            if href:
                news_url = href if href.startswith("http") else url.rstrip("/") + href
                try:
                    r_news = requests.get(news_url, headers=headers, timeout=30)
                    news_soup = BeautifulSoup(r_news.text, "html.parser")
                    news_block = (
                        news_soup.find("article") or
                        news_soup.find("div", class_=re.compile(r"news|artikel", re.IGNORECASE)) or
                        news_soup.find("main") or
                        news_soup
                    )
                    text = news_block.get_text()
                    hits = extract_hits_with_context(text)
                    return hits, text, news_url
                except Exception:
                    continue

        main = soup.find("main") or soup
        text = main.get_text()
        hits = extract_hits_with_context(text)
        return hits, text, url

    except Exception as e:
        print(f"⚠️ Fel vid kontroll av {url}: {e}")
        return [], "", url

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
    seen_kommuner = set()

    with open("kommuner.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kommun = row["kommun"]
            url = row["webbplats"]

            if kommun in seen_kommuner:
                continue
            seen_kommuner.add(kommun)

            hits, full_text, actual_url = check_url(url)
            if hits:
                date = None
                for _, context in hits:
                    date = extract_date(context)
                    if date:
                        break

                if not date:
                    date = extract_date(full_text)

                if date:
                    alert_text = f"{kommun} har infört bevattningsförbud den {date}. Se länk för mer information: <a href='{actual_url}'>{actual_url}</a>"
                else:
                    alert_text = f"{kommun} har infört bevattningsförbud. Se länk för mer information: <a href='{actual_url}'>{actual_url}</a>"

                alerts.append(alert_text)

    if alerts:
        body = "<br><br>".join(alerts)
        send_email(
            f"Bevattningsförbud upptäckt {datetime.today().date()}",
            body
        )

if __name__ == "__main__":
    main()
