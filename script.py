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
    "kalkning"
]

FIXED_FORBUD_KOMMUNER = ["tibro"]

def extract_hits_with_context(text):
    results = []
    lines = text.split("\n")

    for line in lines:
        line_clean = line.strip()
        line_lower = line_clean.lower()

        if not line_clean:
            continue

        if any(neg in line_lower for neg in NEGATIVE_PHRASES) and any(key in line_lower for key in KEYWORDS):
            continue

        if any(key in line_lower for key in KEYWORDS):
            results.append(("bevattningsförbud", line_clean))

    return results

def has_negative_phrase_in_text(text):
    return any(phrase in text.lower() for phrase in NEGATIVE_PHRASES)

def extract_date(text):
    text = text.lower()

    # Matcha "från och med 22 juli"
    pattern1 = re.compile(
        r"från och med (\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        re.IGNORECASE
    )
    match = pattern1.search(text)
    if match:
        return f"{int(match.group(1))} {match.group(2)}"

    # Matcha "22 juli"
    pattern2 = re.compile(
        r"(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        re.IGNORECASE
    )
    match = pattern2.search(text)
    if match:
        return f"{int(match.group(1))} {match.group(2)}"

    # Matcha "2025-07-22"
    match_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if match_iso:
        try:
            date = datetime.strptime(match_iso.group(0), "%Y-%m-%d")
            return date.strftime("%-d %B").lower()
        except:
            pass

    return None

def is_fixed_forbud(kommun, text):
    if kommun.lower() in FIXED_FORBUD_KOMMUNER:
        if re.search(r"tillsvidare|ständigt|permanent|alltid", text.lower()):
            return True
    return False

def check_url(url, kommun):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")

        # Nyhetssökning – hitta alla länkar som innehåller "bevattning"
        links = soup.find_all("a", href=True)
        relevant_links = []

        for a in links:
            href = a.get("href", "")
            text = a.get_text().lower()
            if "bevattning" in href.lower() or "bevattning" in text:
                full_url = href if href.startswith("http") else url.rstrip("/") + href
                relevant_links.append(full_url)

        # Kontrollera varje relevant länk
        for news_url in relevant_links:
            try:
                r_news = requests.get(news_url, headers=headers, timeout=30)
                news_soup = BeautifulSoup(r_news.text, "html.parser")
                news_block = (
                    news_soup.find("article") or
                    news_soup.find("div", class_=re.compile(r"news|artikel", re.IGNORECASE)) or
                    news_soup.find("main") or
                    news_soup
                )
                text = news_block.get_text(separator="\n")

                if has_negative_phrase_in_text(text) or is_fixed_forbud(kommun, text):
                    return [], text, news_url

                hits = extract_hits_with_context(text)
                if hits:
                    return hits, text, news_url

            except Exception:
                continue

        # Fallback till startsidan
        main = soup.find("main") or soup
        text = main.get_text(separator="\n")

        print(f"[DEBUG fallback-text från {kommun}]")
        print(text[:1500])  # Begränsa till 1500 tecken för läsbarhet

        if has_negative_phrase_in_text(text) or is_fixed_forbud(kommun, text):
            return [], text, url

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

            hits, full_text, actual_url = check_url(url, kommun)
            if hits:
                date = None
                for _, context in hits:
                    d = extract_date(context)
                    if d:
                        date = d
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
