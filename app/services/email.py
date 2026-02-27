"""Email sending service — SMTP and SES backends."""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


async def send_email_smtp(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str = "",
    from_name: str = "",
    from_email: str = "",
) -> bool:
    """Send a single email via SMTP."""
    from_name = from_name or settings.smtp_from_name
    from_email = from_email or settings.smtp_from_email

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
        )
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


async def send_email_ses(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str = "",
    from_name: str = "",
    from_email: str = "",
) -> bool:
    """Send a single email via Amazon SES."""
    import boto3

    from_name = from_name or settings.smtp_from_name
    from_email = from_email or settings.smtp_from_email

    client = boto3.client(
        "ses",
        region_name=settings.aws_region,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
    )

    body = {"Html": {"Charset": "UTF-8", "Data": html_body}}
    if text_body:
        body["Text"] = {"Charset": "UTF-8", "Data": text_body}

    try:
        client.send_email(
            Source=f"{from_name} <{from_email}>",
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Charset": "UTF-8", "Data": subject},
                "Body": body,
            },
        )
        logger.info(f"SES email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"SES failed for {to_email}: {e}")
        return False


async def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str = "",
    from_name: str = "",
    from_email: str = "",
) -> bool:
    """Route to configured backend."""
    if settings.mail_backend == "ses":
        return await send_email_ses(to_email, subject, html_body, text_body, from_name, from_email)
    return await send_email_smtp(to_email, subject, html_body, text_body, from_name, from_email)
