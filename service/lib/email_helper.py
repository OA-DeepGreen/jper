import smtplib
from email.message import EmailMessage
from octopus.core import app

def send_email_to_admin(subject, message):
    send_email = app.config.get("SEND_EMAIL", False)
    if not send_email:
        return
    from_email = app.config.get("MAIL_FROM_ADDRESS", '')
    to_email = app.config.get("MAIL_ADMIN_ADDRESS", '')
    subject_prefix = app.config.get("MAIL_SUBJECT_PREFIX", '')
    msg = EmailMessage()
    msg.set_content(message)
    msg['Subject'] = f"#{subject_prefix}#{subject}"
    msg['From'] = from_email
    msg['To'] = to_email
    s = smtplib.SMTP('localhost')
    s.send_message(msg)
    s.quit()
    return

