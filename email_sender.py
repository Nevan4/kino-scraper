import smtplib
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any
from jinja2 import Environment, FileSystemLoader

# Load environment variables from .env file
load_dotenv()


class EmailSender:
    def __init__(self, emails_file: str = "emails.txt") -> None:
        self.smtp_server: str = os.getenv("SMTP_SERVER")
        self.smtp_port: int = int(os.getenv("SMTP_PORT"))
        self.sender_email: str = os.getenv("SENDER_EMAIL")
        self.sender_password: str = os.getenv("SENDER_PASSWORD")
        self.recipient_emails: List[str] = self._load_emails_from_file(emails_file)
        self.template_env = Environment(loader=FileSystemLoader(searchpath="templates"))

    @staticmethod
    def get_today_and_end_date(days_ahead: int) -> tuple:
        today = datetime.today()
        end_date = today + timedelta(days=days_ahead) - timedelta(days=1)
        return today, end_date

    @staticmethod
    def _load_emails_from_file(file_path: str) -> List[str]:
        """Load emails from a text file and return as a list."""
        try:
            with open(file_path, "r") as file:
                emails = file.readlines()
            # Clean up the list (strip extra whitespace or newlines)
            return [email.strip() for email in emails if email.strip()]
        except FileNotFoundError:
            print(f"Error: The file '{file_path}' was not found.")
            return []

    def create_email(self, movie_details: List[Dict[str, Any]], days: int, recipient_email: str) -> MIMEMultipart:
        """Create an email message with the movie details."""
        today, end_date = self.get_today_and_end_date(days)
        template = self.template_env.get_template("email_template.html")
        body = template.render(today=today.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'), movie_details=movie_details)

        message = MIMEMultipart()
        message["From"] = self.sender_email
        message["To"] = recipient_email
        message["Subject"] = f"Repertuar nowych filmów na {today.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"
        message.attach(MIMEText(body, "html"))
        return message

    def send_email(self, movie_details: List[Dict[str, Any]], num_days: int) -> None:
        """Compose and send the email with subject and body."""
        for recipient_email in self.recipient_emails:
            message = self.create_email(movie_details, days=num_days, recipient_email=recipient_email)
            try:
                # Connect to the SMTP server
                with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                    server.ehlo()  # Send EHLO to the server (identify yourself)
                    server.starttls()  # Encrypt the connection
                    server.login(self.sender_email, self.sender_password)

                    # Send the email
                    server.sendmail(self.sender_email, recipient_email, message.as_string())
                    print(f"Email sent successfully to {recipient_email}!")

            except Exception as e:
                print(f"Error sending email to {recipient_email}: {e}")
