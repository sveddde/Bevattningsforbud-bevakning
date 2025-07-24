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
CONTEXT_CHARS = 50  # antal tecken före och efter nyckelord


def extract_hits_with_context(text):
    results = []
    for keyword in KEYWORDS:
        for match in re.finditer(keyword, text):
            start = max(0, match.start() - CONTEXT_CHARS)
            end = min(len(text), match.end() + CONTEXT_CHARS)
            context = text[start:end].strip().lower()

            # Uteslut felaktig kontext
            if any(bad in context for bad in ["publicerad", "uppdaterad", "kalkning", "senast ändrad"]):
                continue
            if "inget bevattningsförbud" in context or "inga bevattningsförbud" in context:
                continue

            results.append((keyword, context))
    return results


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


def main():
    alert


if __name__ == "__main__":
    main()
