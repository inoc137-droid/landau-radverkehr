import hashlib
import json
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


STATE_FILE = Path("state.json")

TARGETS = {
    "radverkehr_page": "https://landau.klimaschutzportal.rlp.de/portal/foerderung/radverkehr",
    "sitemap": "https://landau.klimaschutzportal.rlp.de/informationen/sitemap",
    "known_form_pdf": "https://landau.klimaschutzportal.rlp.de/fileadmin/redaktion/kipki/antragsformular_f%C3%B6rderprogramme_ab_202511.pdf",
    "known_guideline_pdf": "https://landau.klimaschutzportal.rlp.de/fileadmin/redaktion/kipki/f%C3%B6rderrichtlinie_radverkehr.pdf",
}

KEYWORDS = [
    "antrag",
    "antragsformular",
    "formular",
    "radverkehr",
    "förderprogramm",
    "foerderprogramm",
    "download",
    "freigeschaltet",
    "neustart",
    "pdf",
    "kipki",
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> requests.Response:
    headers = {
        "User-Agent": "Mozilla/5.0 compatible website-change-monitor/1.0",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r


def normalize_html(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    visible_text = " ".join(soup.get_text(" ", strip=True).split())

    links = []
    relevant_links = []

    for a in soup.find_all("a", href=True):
        link = urljoin(url, a["href"]).split("#")[0]
        text = " ".join(a.get_text(" ", strip=True).split())

        entry = f"{text} -> {link}"
        links.append(entry)

        haystack = f"{text} {link}".lower()
        if any(k.lower() in haystack for k in KEYWORDS):
            relevant_links.append(entry)

    return {
        "visible_text_hash": sha256_text(visible_text),
        "relevant_links_hash": sha256_text("\n".join(sorted(set(relevant_links)))),
        "visible_text_excerpt": visible_text[:1000],
        "relevant_links": sorted(set(relevant_links)),
    }


def snapshot() -> dict:
    result = {}

    for name, url in TARGETS.items():
        r = fetch(url)
        content_type = r.headers.get("content-type", "")

        if "text/html" in content_type:
            parsed = normalize_html(url, r.text)
            result[name] = {
                "url": url,
                "type": "html",
                "status_code": r.status_code,
                **parsed,
            }
        else:
            result[name] = {
                "url": url,
                "type": content_type or "binary",
                "status_code": r.status_code,
                "content_hash": sha256_bytes(r.content),
                "content_length": len(r.content),
            }

    return result


def load_old_state() -> dict | None:
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text(encoding="utf-8"))


def save_state(data: dict) -> None:
    STATE_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def diff_states(old: dict | None, new: dict) -> list[str]:
    if old is None:
        return ["Erster Lauf: Baseline wurde erzeugt."]

    changes = []

    for key, new_item in new.items():
        old_item = old.get(key)

        if old_item is None:
            changes.append(f"Neu beobachtet: {key} ({new_item['url']})")
            continue

        for field in [
            "visible_text_hash",
            "relevant_links_hash",
            "content_hash",
            "content_length",
            "status_code",
        ]:
            if old_item.get(field) != new_item.get(field):
                changes.append(
                    f"Änderung bei {key}: {field}\n"
                    f"URL: {new_item['url']}\n"
                    f"alt: {old_item.get(field)}\n"
                    f"neu: {new_item.get(field)}"
                )

    return changes


def send_email(subject: str, body: str) -> None:
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_password = os.environ["SMTP_PASSWORD"]
    mail_from = os.environ["MAIL_FROM"]
    mail_to = os.environ["MAIL_TO"]

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)


def main():
    if os.environ.get("SEND_TEST_MAIL") == "true":
        send_email(
            subject="Testmail: Landau Radverkehr Monitor",
            body="Das ist eine Testmail. SMTP funktioniert."
        )
        print("Testmail versendet.")
        return

    old = load_old_state()
    new = snapshot()
    changes = diff_states(old, new)

    save_state(new)

    # Beim ersten Lauf keine Alarm-Mail senden, nur Baseline speichern.
    if old is None:
        print("Baseline erzeugt.")
        return

    if changes:
        body = "Änderung erkannt:\n\n" + "\n\n---\n\n".join(changes)

        body += "\n\n\nAktuell relevante Links:\n"
        for key, item in new.items():
            if item.get("relevant_links"):
                body += f"\n[{key}]\n"
                body += "\n".join(item["relevant_links"])
                body += "\n"

        send_email(
            subject="Änderung auf Klimaschutzportal Radverkehr erkannt",
            body=body,
        )
        print("Änderung erkannt, Mail versendet.")
    else:
        print("Keine Änderung.")


if __name__ == "__main__":
    main()
