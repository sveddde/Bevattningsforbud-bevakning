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

KEYWORDS = ["bevattningsförbud"]
CONTEXT_CHARS_BEFORE = 100
CONTEXT_CHARS_AFTER = 50

def extract_hits_with_context(text):
    results = []
    for keyword in KEYWORDS:
        for match in re.finditer(keyword, text):
            start = max(0, match.start() - CONTEXT_CHARS_BEFORE)
            end = min(len(text), match.end() + CONTEXT_CHARS_AFTER)
            context = text[start:end].strip().lower()

            # Uteslut felaktig kontext
            if any(bad in context for bad in ["publicerad", "uppdaterad", "kalkning", "senast ändrad"]):
                continue
            if "inget bevattningsförbud" in context or "inga bevattningsförbud" in context:
                continue

            results.append((keyword, context))
    return results

# I den kod där du hämtar datum från context:
date = extract_date(context)
if not date:
    # Nytt! Prova hela texten om datum inte hittades
    date = extract_date(full_text)

# full_text = hela nyhetstexten (inte bara context)

def extract_date(context):
    context = context.lower()

    # Matcha meningsfulla fraser som innebär införandedatum
    pattern = re.compile(
        r"(från och med|införs|gäller från och med|träder i kraft)?\s*(\d{1,2})\s+(januari|februari|mars|april|maj|juni|juli|augusti|september|oktober|november|december)",
        re.IGNORECASE
    )
    match = pattern.search(context)
    if match:
        return f"{match.group(2)} {match.group(3).lower()}"

    # Alternativt: ISO-format
    match_iso = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", context)
    if match_iso:
        try:
            date = datetime.strptime(match_iso.group(0), "%Y-%m-%d")
            return date.strftime("%-d %B")
        except:
            pass

    return None
def find_relevant_news(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    r = requests.get(url, headers=headers, timeout=30)
    soup = BeautifulSoup(r.text, "html.parser")

    # Hitta alla länkar till bevattningsförbud
    a_tags = soup.find_all("a", string=re.compile(r"bevattningsförbud", re.IGNORECASE))
    news_candidates = []

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
                text = news_block.get_text().lower()
                date_str = extract_date(text)
                if date_str:
                    try:
                        date_obj = datetime.strptime(date_str, "%d %B")
                        date_obj = date_obj.replace(year=datetime.now().year)
                        news_candidates.append((date_obj, news_url, text))
                    except Exception:
                        pass
            except Exception:
                continue

    today = datetime.now()
    valid_candidates = [c for c in news_candidates if c[0] >= today]
    if valid_candidates:
        relevant = min(valid_candidates, key=lambda x: x[0])
    elif news_candidates:
        relevant = max(news_candidates, key=lambda x: x[0])
    else:
        relevant = None

    return relevant  # tuple: (date_obj, news_url, text)
    

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

        # Steg 2: Leta efter länk till "bevattningsförbud"
        a_tags = soup.find_all("a", string=re.compile(r"bevattningsförbud", re.IGNORECASE))
        news_url = None
        for a in a_tags:
            href = a.get("href")
            if href:
                if href.startswith("http"):
                    news_url = href
                else:
                    news_url = url.rstrip("/") + href
                break  # Ta första träffen

        # Steg 3: Hämta nyhetssidan (rätt artikel)
        if news_url:
            print(f"🔗 Följer nyhetslänk: {news_url}")
            r = requests.get(news_url, headers=headers, timeout=30)
            soup = BeautifulSoup(r.text, "html.parser")

            # Försök plocka bara innehållet i själva nyheten
            # Exempelvis från en <article> eller ett nyhetsblock
            news_block = (
                soup.find("article") or
                soup.find("div", class_=re.compile(r"news|artikel", re.IGNORECASE)) or
                soup.find("main") or
                soup
            )
        else:
            news_block = soup.find("main") or soup

        text = news_block.get_text().lower()
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


def main():
    with open("kommuner.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kommun_namn = row.get("kommun") or row.get("namn") or "Kommun"
            kommun_url = row.get("url")
            if not kommun_url:
                continue

            print(f"🔎 Kollar {kommun_namn}: {kommun_url}")
            result = find_relevant_news(kommun_url)
            if result:
                date_obj, news_url, news_text = result
                body = (
                    f"<b>{kommun_namn}:</b><br>"
                    f"Bevattningsförbud gäller från: {date_obj.strftime('%d %B')}.<br>"
                    f"Läs mer: <a href='{news_url}'>{news_url}</a>"
                )
                send_email(
                    f"Bevattningsförbud - {kommun_namn}",
                    body
                )
            else:
                send_email(
                    f"Bevattningsförbud - {kommun_namn}",
                    f"Ingen relevant nyhet hittades för {kommun_namn}."
                )


if __name__ == "__main__":
    main()
