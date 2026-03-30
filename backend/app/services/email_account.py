from __future__ import annotations

import email
import imaplib
import smtplib
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr

from sqlalchemy.orm import Session

from app.models.models import Email
from app.schemas.email import EmailIngestRequest
from app.schemas.tasking import AccountConnectionResult, InboxSyncRequest, InboxSyncResponse


class EmailAccountError(Exception):
    pass


def test_email_account_connection(payload: InboxSyncRequest) -> AccountConnectionResult:
    imap_ok = False
    smtp_ok = False

    try:
        with imaplib.IMAP4_SSL(payload.imap_host, payload.imap_port) as client:
            client.login(payload.email_address, payload.password)
        imap_ok = True
    except Exception as exc:
        raise EmailAccountError(f"IMAP connection failed: {exc}") from exc

    try:
        with smtplib.SMTP(payload.smtp_host or "smtp.gmail.com", payload.smtp_port or 587, timeout=20) as smtp:
            if payload.use_tls:
                smtp.starttls()
            smtp.login(payload.email_address, payload.password)
        smtp_ok = True
    except Exception as exc:
        raise EmailAccountError(f"SMTP connection failed: {exc}") from exc

    return AccountConnectionResult(imap_ok=imap_ok, smtp_ok=smtp_ok, message="IMAP and SMTP are working.")


def sync_inbox(db: Session, payload: InboxSyncRequest) -> InboxSyncResponse:
    imported = 0
    queued = 0

    try:
        with imaplib.IMAP4_SSL(payload.imap_host, payload.imap_port) as client:
            client.login(payload.email_address, payload.password)
            client.select(payload.mailbox)

            criteria = "(UNSEEN)" if payload.unread_only else "ALL"
            _, data = client.search(None, criteria)
            message_numbers = data[0].split()
            target_numbers = message_numbers[-payload.limit :]

            for number in target_numbers:
                _, fetched = client.fetch(number, "(RFC822)")
                raw_bytes = fetched[0][1]
                parsed = email.message_from_bytes(raw_bytes)
                message_id = parsed.get("Message-ID") or f"imap-{number.decode()}"

                existing = db.query(Email).filter(Email.message_id == message_id).first()
                if existing is not None:
                    continue

                subject = decode_mime_header(parsed.get("Subject", "(no subject)"))
                from_address = parseaddr(parsed.get("From", ""))[1] or payload.email_address
                to_address = parseaddr(parsed.get("To", ""))[1] or payload.email_address
                raw_body = extract_body(parsed)

                email_record = Email(
                    message_id=message_id,
                    thread_id=parsed.get("Thread-Index"),
                    subject=subject,
                    raw_body=raw_body,
                    cleaned_body=raw_body.strip(),
                    from_address=from_address,
                    to_address=to_address,
                    source="imap",
                    status="QUEUED",
                )
                db.add(email_record)
                db.commit()
                db.refresh(email_record)

                imported += 1
                queued += 1

    except Exception as exc:
        raise EmailAccountError(f"Inbox sync failed: {exc}") from exc

    return InboxSyncResponse(
        imported=imported,
        queued=queued,
        message=f"Imported {imported} email(s) and queued {queued} for processing.",
    )


def send_smtp_email(recipient: str, subject: str, body: str, sender: str, password: str, host: str, port: int, use_tls: bool) -> None:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(host, port, timeout=20) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(sender, password)
        smtp.send_message(message)


def decode_mime_header(value: str) -> str:
    return str(make_header(decode_header(value)))


def extract_body(message: email.message.Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", ""))
            if content_type == "text/plain" and "attachment" not in disposition:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")

        for part in message.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")

    payload = message.get_payload(decode=True)
    if payload is None:
        return ""
    charset = message.get_content_charset() or "utf-8"
    return payload.decode(charset, errors="replace")
