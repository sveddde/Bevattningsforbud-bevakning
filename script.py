import csv
import os
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
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
    "är inte längre aktuellt",
    "förbudet har upphört",
    "bevattningsförbudet har upphört",
    "förbudet har avslutats",
    "förbudet gäller inte längre",
    "förbudet är avslutat",
    "inte längre ett bevattningsförbud"
]

BLOCKED_URL_PATTERNS = [
    "upphavt", "upphört", "upphävt", "upphort", "avslutat", "slut"
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

    pattern1 = re.compile(
        r"från och med (\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        re.IGNORECASE
    )
    match = pattern1.search(text)
    if match:
        return f"{int(match.group(1))} {match.group(2)}"

    pattern2 = re.compile(
        r"(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        re.IGNORECASE
    )
    match = pattern2.search(text)
    if match:
        return f"{int(match.group(1))} {match.group(2)}"

    match_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
    if match_iso:
        try:
            date = datetime.strptime(match_iso.group(0), "%Y-%m-%d")
            return date.strftime("%-d %B").lower()
        except:
            pass

    return None

def is_recent_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%d %B")
        dt = dt.replace(year=datetime.today().year)
        return dt >= datetime.today() - timedelta(days=120)
    except:
        return False

def is_fixed_forbud(kommun, text):
    if kommun.lower() in FIXED_FORBUD_KOMMUNER:
        if re.search(r"tillsvidare|ständigt|permanent|alltid", text.lower()):
            return True
    return False

def is_blocked_url(url):
    url_lower = url.lower()
    return any(pattern in url_lower for pattern in BLOCKED_URL_PATTERNS)

def check_url(url, kommun):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        r = requests.get(url, headers=headers, timeout=30)
        soup = BeautifulSoup(r.text, "html.parser")

        links = soup.find_all("a", href=True)
        relevant_links = []

        for a in links:
            href = a.get("href", "")
            text = a.get_text().lower()
            if ("bevattning" in href.lower() or "bevattning" in text or "bevattningsförbud" in text):
                full_url = href if href.startswith("http") else url.rstrip("/") + href
                if not is_blocked_url(full_url):
                    relevant_links.append(full_url)

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
                for _, ctx in hits:
                    extracted = extract_date(ctx)
                    if extracted and is_recent_date(extracted):
                        return [(_, ctx)], text, news_url

            except Exception:
                continue

        main = soup.find("main") or soup
        text = main.get_text(separator="\n")

        if has_negative_phrase_in_text(text) or is_fixed_forbud(kommun, text) or is_blocked_url(url):
            return [], text, url

        hits = extract_hits_with_context(text)
        for _, ctx in hits:
            extracted = extract_date(ctx)
            if extracted and is_recent_date(extracted):
                return [(_, ctx)], text, url

        return [], text, url

    except Exception as e:
        print(f"⚠️ Fel vid kontroll av {url}: {e}")
        return [], "", url

def send_email(subject, body):
    print(f"DEBUG: Skickar mail med ämne: {subject}")
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
                _, context = hits[0]
                date = extract_date(context)

                if not (date and is_recent_date(date)):
                    date = extract_date(full_text)

                if date:
                    alert_text = f"{kommun} har infört bevattningsförbud den {date}. Se länk för mer information: <a href='{actual_url}'>{actual_url}</a>"
                else:
                    alert_text = f"{kommun} har infört bevattningsförbud. Se länk för mer information: <a href='{actual_url}'>{actual_url}</a>"

                alerts.append(alert_text)

    print(f"DEBUG: Antal bevattningsförbud som hittats: {len(alerts)}")
    for alert in alerts:
        print(f"DEBUG ALERT: {alert}")

    if alerts:
        body = "<br><br>".join(alerts)
        send_email(
            f"Bevattningsförbud upptäckt {datetime.today().date()}",
            body
        )

if __name__ == "__main__":
    main()
