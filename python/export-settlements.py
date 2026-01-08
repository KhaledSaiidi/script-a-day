#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from urllib.request import urlopen

import smtplib
from email.message import EmailMessage
from playwright.sync_api import sync_playwright

BILATERAL_REPORT_URL = "https://finance-portal.int.kabiloo.ml.gisp.gm/api/reports/report-bilateral-settlement"
DFSP_DETAIL_URL = "https://finance-portal.int.kabiloo.ml.gisp.gm/api/reports/dfspSettlementDetail"
SETTLEMENT_JSON_URL = "https://finance-portal.int.gisp-stg.ml.gisp.gm/api/central-settlements/settlements"


def render_pdf(page, url: str, output: Path) -> None:
    page.goto(url, wait_until="networkidle", timeout=120_000)
    page.add_style_tag(content="""
        * { -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }
    """)
    page.pdf(
        path=str(output),
        landscape=False,
        scale=0.8,
        print_background=True,
        display_header_footer=False,
        prefer_css_page_size=True,
    )


def download_json(url: str, output: Path) -> None:
    with urlopen(url, timeout=120) as resp:
        output.write_bytes(resp.read())


def download_file(url: str, output: Path) -> None:
    with urlopen(url, timeout=120) as resp:
        output.write_bytes(resp.read())


def send_email(
    *,
    smtp_host: str,
    smtp_port: int,
    username: str,
    password: str,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    attachments: list[Path],
) -> None:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(body)

    for attachment in attachments:
        msg.add_attachment(
            attachment.read_bytes(),
            maintype="application",
            subtype="octet-stream",
            filename=attachment.name,
        )

    with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=60) as smtp:
        smtp.login(username, password)
        smtp.send_message(msg)


def main() -> int:
    if len(sys.argv) not in (5, 6):
        print(
            "Usage: export_dfsp_settlement_detail_pdf.py <settlementId> <yyyymmdd> <fspId1> <fspId2> [fspId3]",
            file=sys.stderr,
        )
        return 2

    settlement_id = sys.argv[1]
    settlement_date = sys.argv[2]
    fsp_id_1 = sys.argv[3]
    fsp_id_2 = sys.argv[4]
    fsp_id_3 = sys.argv[5] if len(sys.argv) == 6 else None

    bilateral_pdf = Path(f"Bilateral-Net-Settlement-Report-{settlement_id}.pdf").resolve()
    bilateral_csv = Path(f"Bilateral-Net-Settlement-Report-{settlement_id}-csv.csv").resolve()
    bilateral_json = Path(f"Bilateral-Net-Settlement-Report-{settlement_id}.json").resolve()
    dfsp_pdf_1 = Path(f"dfsp-settlement-detail-{settlement_id}-{fsp_id_1}.pdf").resolve()
    dfsp_pdf_2 = Path(f"dfsp-settlement-detail-{settlement_id}-{fsp_id_2}.pdf").resolve()
    dfsp_pdf_3 = (
        Path(f"dfsp-settlement-detail-{settlement_id}-{fsp_id_3}.pdf").resolve()
        if fsp_id_3
        else None
    )

    bilateral_url = f"{BILATERAL_REPORT_URL}?settlementId={settlement_id}&format=html"
    bilateral_csv_url = f"{BILATERAL_REPORT_URL}?settlementId={settlement_id}&format=csv"
    settlement_json_url = f"{SETTLEMENT_JSON_URL}/{settlement_id}"
    dfsp_url_1 = f"{DFSP_DETAIL_URL}?settlementId={settlement_id}&fspId={fsp_id_1}"
    dfsp_url_2 = f"{DFSP_DETAIL_URL}?settlementId={settlement_id}&fspId={fsp_id_2}"
    dfsp_url_3 = (
        f"{DFSP_DETAIL_URL}?settlementId={settlement_id}&fspId={fsp_id_3}"
        if fsp_id_3
        else None
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        page = browser.new_page(viewport={"width": 1920, "height": 1080})

        # 1) Bilateral net settlement PDF
        render_pdf(page, bilateral_url, bilateral_pdf)

        # 1b) Bilateral net settlement CSV
        download_file(bilateral_csv_url, bilateral_csv)

        # 2) Settlement JSON
        download_json(settlement_json_url, bilateral_json)

        # 3) DFSP detail PDF for first FSP
        render_pdf(page, dfsp_url_1, dfsp_pdf_1)

        # 4) DFSP detail PDF for second FSP
        render_pdf(page, dfsp_url_2, dfsp_pdf_2)

        # 5) DFSP detail PDF for third FSP (optional)
        if fsp_id_3:
            render_pdf(page, dfsp_url_3, dfsp_pdf_3)

        browser.close()

    print("Wrote:")
    print(f"  {bilateral_pdf}")
    print(f"  {bilateral_csv}")
    print(f"  {bilateral_json}")
    print(f"  {dfsp_pdf_1}")
    print(f"  {dfsp_pdf_2}")
    if dfsp_pdf_3:
        print(f"  {dfsp_pdf_3}")

    smtp_host = "smtp.gmail.com"
    smtp_port = 465
    sender = os.getenv("GMAIL_SENDER", "khaled.saidi@infitx.com")
    recipient = os.getenv("GMAIL_RECIPIENT", "support@infitx.com")
    username = os.getenv("GMAIL_USERNAME", sender)
    password = os.getenv("GMAIL_APP_PASSWORD")
    if not password:
        print("Missing GMAIL_APP_PASSWORD; skipping email send.", file=sys.stderr)
        return 0

    attachments = [bilateral_pdf, bilateral_csv, bilateral_json, dfsp_pdf_1, dfsp_pdf_2]
    if dfsp_pdf_3:
        attachments.append(dfsp_pdf_3)

    subject = f"{settlement_date} settlement report {settlement_id} approval"
    body = (
        f"attached the settlement report  {settlement_id}  for the "
        f"{settlement_date} settlement window approval"
    )
    send_email(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        username=username,
        password=password,
        sender=sender,
        recipient=recipient,
        subject=subject,
        body=body,
        attachments=attachments,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ~/Downloads/settlements ❯ source .venv/bin/activate
# ~/Downloads/settlements ❯ python export_dfsp_settlement_detail_pdf.py 1 reliance

