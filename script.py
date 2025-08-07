import csv
import os
import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
import re
from urllib.parse import urljoin

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

def extract_hits_with_context(soup, base_url, keywords):
    hits = []
    all_text_elements = soup.find_all(string=True)

    for element in all_text_elements:
        if any(keyword.lower() in element.lower() for keyword in keywords):
            parent = element.parent
            for _ in range(3):
                if parent.name != 'a' and parent.find('a'):
                    parent = parent.find('a')
                elif parent.parent:
                    parent = parent.parent

            href = parent.get('href') if parent else None
            if href:
                href = urljoin(base_url, href)

            context_parts = []
            if element.parent and element.parent.parent:
                for text in element.parent.parent.stripped_strings:
                    context_parts.append(text.strip())
            context = " ".join(context_parts)

            sentences = re.split(r'(?:\n|\r|\r\n|(?<=[.!?])\s+)', context)
            for sentence in sentences:
                if any(keyword.lower() in sentence.lower() for keyword in keywords):
                    hits.append((sentence.strip(), href))
                    break
            else:
                if any(keyword.lower() in context.lower() for keyword in keywords):
                    hits.append((context.strip(), href))

    return hits

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

        # Försök med nyhetslänkar först (t.ex. Orust)
        nyhetslänkar = soup.find_all("a", href=re.compile(r"/nyheter/", re.IGNORECASE))
        for a in nyhetslänkar:
            href = a.get("href")
            if href:
                news_url = href if href.startswith("http") else url.rstrip("/") + href
                try:
                    r_news = requests.get(news_url, headers=headers, timeout=30)
                    news_soup = BeautifulSoup(r_news.text, "html.parser")

                    text_lower = news_soup.get_text().lower()
                    if any(neg in text_lower for neg in NEGATIVE_PHRASES):
                        continue

                    hits = extract_hits_with_context(news_soup, news_url, KEYWORDS)
                    if hits:
                        return hits, news_soup.get_text(), news_url
                except Exception:
                    continue

        # Vanlig sökning på startsidan
        hits = extract_hits_with_context(soup, url, KEYWORDS)
        if hits:
            return hits, soup.get_text(), url

        return [], "", url

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
                for context, _ in hits:
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
