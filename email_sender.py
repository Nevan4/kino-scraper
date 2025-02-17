import smtplib
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any

# Load environment variables from .env file
load_dotenv()


class EmailSender:
    def __init__(self, emails_file: str = "emails.txt") -> None:
        self.smtp_server: str = os.getenv("SMTP_SERVER")
        self.smtp_port: int = int(os.getenv("SMTP_PORT"))
        self.sender_email: str = os.getenv("SENDER_EMAIL")
        self.sender_password: str = os.getenv("SENDER_PASSWORD")
        self.recipient_emails: List[str] = self._load_emails_from_file(emails_file)

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

    def create_email(self, movie_details: List[Dict[str, Any]], days: int) -> MIMEMultipart:
        """Create an email message with the movie details."""
        today, end_date = self.get_today_and_end_date(days)
        message = MIMEMultipart()
        message["From"] = self.sender_email
        message["To"] = ", ".join(self.recipient_emails)
        message["Subject"] = f"Repertuar nowych filmów na {today.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}"

        # Start of the HTML body
        body = """
        <html>
        <head>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    color: #333333;
                }
                h1 {
                    color: #2a5d84;
                }
                .movie {
                    border-bottom: 2px solid #cccccc;
                    padding: 10px 0;
                    margin: 20px 0;
                }
                .movie-title {
                    font-size: 24px;
                    color: #2a5d84;
                }
                .movie-details {
                    margin: 10px 0;
                    font-size: 14px;
                }
                .screening-times {
                    background-color: #f0f0f0;
                    padding: 10px;
                    border-radius: 5px;
                }
                .screening-time {
                    margin: 5px 0;
                }
            </style>
        </head>
        <body>
        """

        # Append the dynamic date range to the body
        body += f"<h1>Nowe filmy na: {today.strftime('%Y-%m-%d')} - {end_date.strftime('%Y-%m-%d')}</h1>"

        # Loop through each movie and build the HTML body
        for movie in movie_details:
            title = movie.get('title', 'No Title')
            link = movie.get('link', 'No Link')
            genre = movie.get('genre', 'No Genre')
            description = movie.get('description', 'No Description')
            production_year = movie.get('production_year', 'No Year')
            screenings = movie.get('screening_times', [])

            # Build the movie details block
            body += f"""
            <div class="movie">
                <div class="movie-title">
                    <a href="{link}" target="_blank" style="text-decoration: none; color: #007bff; font-weight: bold;">
                        {title}
                    </a>
                </div>
                <div class="movie-details">
                    <strong>Gatunek:</strong> {genre}<br>
                    <strong>Opis:</strong> {description}<br>
                    <strong>Rok Produkcji:</strong> {production_year}
                </div>
                <div class="screening-times">
                    <strong>Godziny Seansów:</strong>
                    <div>
            """

            # Add screening times
            added_screening = False
            if screenings:
                for screening in screenings:
                    date = screening.get('date', 'No Date')
                    times = ', '.join(screening.get('times', [])) if screening.get('times') else None

                    if not times:
                        continue

                    body += f'<div class="screening-time">{date}: {times}</div>'
                    added_screening = True

                if not added_screening:
                    body += "<div class='screening-time'>No upcoming screenings available</div>"
            else:
                body += "<div class='screening-time'>No screening times available</div>"

            body += "</div></div></div>"

        # End of the HTML body
        body += """
        </body>
        </html>
        """

        # Attach the HTML body to the email message
        message.attach(MIMEText(body, "html"))
        return message

    def send_email(self, movie_details: List[Dict[str, Any]], num_days: int) -> None:
        """Compose and send the email with subject and body."""
        message = self.create_email(movie_details, days=num_days)
        try:
            # Connect to the SMTP server
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.ehlo()  # Send EHLO to the server (identify yourself)
                server.starttls()  # Encrypt the connection
                server.login(self.sender_email, self.sender_password)

                # Send the email
                server.sendmail(self.sender_email, self.recipient_emails, message.as_string())
                print("Email sent successfully!")

        except Exception as e:
            print(f"Error sending email: {e}")
