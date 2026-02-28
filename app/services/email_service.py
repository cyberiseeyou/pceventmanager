"""
Email Service
Sends HTML emails via SMTP using stdlib modules.
Reads SMTP configuration from SystemSetting.
"""
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_TIMEOUT = 30


class EmailService:
    """Sends emails via configurable SMTP server."""

    def __init__(self, host, port, username, password, sender_email, use_tls=True):
        self.host = host
        self.port = int(port)
        self.username = username
        self.password = password
        self.sender_email = sender_email
        self.use_tls = use_tls

    @classmethod
    def from_settings(cls, SystemSetting):
        """Build an EmailService from SystemSetting values.

        Returns:
            EmailService instance, or None if SMTP is not configured.
        """
        host = SystemSetting.get_setting('smtp_host')
        if not host:
            return None

        return cls(
            host=host,
            port=SystemSetting.get_setting('smtp_port', '587'),
            username=SystemSetting.get_setting('smtp_username', ''),
            password=SystemSetting.get_setting('smtp_password', ''),
            sender_email=SystemSetting.get_setting(
                'smtp_sender_email', 'mat.conder@productconnections.com'
            ),
            use_tls=SystemSetting.get_setting('smtp_use_tls', True),
        )

    def send_html_email(self, to, subject, html):
        """Send an HTML email.

        Args:
            to: Recipient address or list of addresses.
            subject: Email subject line.
            html: HTML body content.

        Raises:
            smtplib.SMTPException on delivery failure.
        """
        if isinstance(to, str):
            to = [addr.strip() for addr in to.split(',') if addr.strip()]

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.sender_email
        msg['To'] = ', '.join(to)
        msg.attach(MIMEText(html, 'html'))

        logger.info(f"Sending email to {to} via {self.host}:{self.port}")

        with smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT) as server:
            if self.use_tls:
                server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.sendmail(self.sender_email, to, msg.as_string())

        logger.info("Email sent successfully")
