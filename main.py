#!/usr/bin/env python3
import json
import logging
import requests
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from logger_config import configure_logger, configure_movie_logger
from email_sender import EmailSender
from database import Database
from typing import Dict, List, Tuple, Union

# Define the base URL as a module-level constant
BASE_URL = "https://www.kinonh.pl/"


class KinoScraper:
    def __init__(self, base_url: str = BASE_URL, db_name: str = "movies.db") -> None:
        self.base_url = base_url
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/114.0.0.0 Safari/537.36"
        }
        self.movies: Dict[str, Dict[str, Union[str, Dict[str, List[str]]]]] = {}
        # Configure logging for this class
        self.logger = configure_logger(
            self.__class__.__name__,
            log_file="kino_scraper.log",
            level=logging.DEBUG
        )
        self.logger.info("\n\nKinoScraper initialized.")
        self.movies_logger = configure_movie_logger(
            f"{self.__class__.__name__}_movies",
            log_file="movies_updated.log",
            level=logging.DEBUG
        )
        self.logger.info("\n\nMovies logger initialized.")

        # Initialize the Database
        self.db = Database(db_name)
        self.db.connect()
        self.db.initialize_schema()  # Ensure schema is set up

    def _get_dates_range(self) -> List[str]:
        """Get a list of dates for the next 10 days."""
        dates = [(datetime.today() + timedelta(days=i)).strftime("%d-%m-%Y") for i in range(10)]
        self.logger.debug(f"Fetching movies for dates: {dates}")
        return dates

    def _get_existing_movies(self) -> List[Tuple[str, str]]:
        """Retrieve all movie titles and years already stored in the database."""
        return self.db.fetch_movie_titles_and_years()

    def _fetch_movies_page(self, formatted_date: str) -> Union[Dict[str, str], None]:
        """Fetch the movies page for a given date."""
        url_for_json = f"{self.base_url}/rep.json?dzien={formatted_date}"
        self.logger.info(f"Fetching movies page for date: {formatted_date}")
        response = requests.get(url_for_json, headers=self.headers)
        if response.status_code == 200:
            self.logger.info(f"Successfully fetched movies page for date: {formatted_date}")
            return response.json().get("lista", "")  # default value if the key doesn't exist
        else:
            self.logger.error(f"Failed to fetch movies page. Status code: {response.status_code}")
            return None

    def _parse_movies(self, formatted_date: str) -> None:
        """Parse the movies for a given date."""
        existing_movies = self._get_existing_movies()

        raw_html = self._fetch_movies_page(formatted_date)
        if not raw_html:
            self.logger.debug(f"Cannot fetch the movie page for {formatted_date}")
            return

        self.logger.info(f"Parsing movies for {formatted_date}...")
        soup = BeautifulSoup(raw_html, 'html.parser')
        for event in soup.find_all('div', class_='pastyt'):
            title_tag = event.find('a', class_='tyt')
            if title_tag:
                title = title_tag.text.strip()
                link = f"{self.base_url}{title_tag['href']}"

                # Check if the movie is already in the database
                if any(movie[0] == title for movie in existing_movies):
                    self.logger.info(f"Movie '{title}' already exists in the database")
                    continue  # skip this movie if in database

                # Find the screening times
                times_div = event.find_next_sibling('div', class_='seanserep')
                screening_times = [a.text.strip() for a in times_div.find_all('a', class_='xseans')] if times_div else []

                if title not in self.movies:
                    self.movies[title] = {"title": title, "link": link, "screenings": {}}
                self.movies[title]["screenings"][formatted_date] = screening_times
                self.logger.debug(f"Parsed movie: {title} for {formatted_date}")

    def _clean_genre_text(self, genre_text: str) -> str:
        """Clean the genre text by removing 'gatunek:' and 'kategoria wiekowa:', and trimming any extra spaces."""
        # Remove 'gatunek:' if present
        if "gatunek:" in genre_text:
            genre_text = genre_text.split("gatunek:")[1].strip()

        # Remove 'kategoria wiekowa:' if present
        if "kategoria wiekowa:" in genre_text:
            genre_text = genre_text.split("kategoria wiekowa:")[0].strip()

        # Remove 'czas trwania:' and everything after it
        if "czas trwania:" in genre_text:
            genre_text = genre_text.split("czas trwania:")[0].strip()

        return genre_text

    def _clean_production_text(self, production_text: str) -> Tuple[str, str]:
        """Extract countries and year separately from production text."""
        if "produkcja:" in production_text.lower():
            production_text = production_text.replace("produkcja:", "").strip()

        # Regular expression to extract the year (assuming it's always a 4-digit number at the end)
        year_match = re.search(r'(\d{4})$', production_text)
        year = year_match.group(1) if year_match else "Unknown"

        # Extract country names (removing the year part)
        countries = production_text.replace(year, "").strip() if year_match else production_text

        return countries, year

    def _fetch_genre(self, soup: BeautifulSoup) -> Tuple[str, Union[BeautifulSoup, None]]:
        """Fetch and return the movie genre from the movie page."""
        genre_h4 = next((h4 for h4 in soup.find_all('h4') if 'gatunek' in h4.get_text().lower()), None)
        if genre_h4:
            genre_text = genre_h4.get_text().strip()
            return self._clean_genre_text(genre_text), genre_h4.find_parent()
        return "Genre not found", None

    def _fetch_description(self, soup: BeautifulSoup, parent_div: Union[BeautifulSoup, None] = None) -> str:
        """Fetch and return the movie description from the movie page."""
        if parent_div:
            paragraphs = [p.text.strip() for p in parent_div.find_all('p') if p.text.strip()]
            return "\n".join(paragraphs) if paragraphs else "Description not found"
        description_h4 = next((h4 for h4 in soup.find_all('h4') if 'opis' in h4.get_text().lower()), None)
        if description_h4:
            parent_div = description_h4.find_parent()
            if parent_div:
                paragraphs = [p.text.strip() for p in parent_div.find_all('p') if p.text.strip()]
                return "\n".join(paragraphs) if paragraphs else "Description not found"
        return "Description not found"

    def _fetch_production(self, soup: BeautifulSoup) -> Tuple[str, str]:
        """Fetch and return the production details from the movie page."""
        # Look for any divs that might contain production information
        production_divs = soup.find_all('div', class_='f4 crrow')
        for div in production_divs:
            if 'produkcja:' in div.text.lower():  # Check if 'produkcja' is mentioned in the div
                production = div.text.strip()
                countries, year = self._clean_production_text(production)
                return countries, year
        return "Unknown", "Unknown"

    def _fetch_movie_details(self, movie: Dict[str, Union[str, Dict[str, List[str]]]]) -> None:
        """Fetch the genre, description, and production details for a movie."""
        self.logger.info(f"Fetching details for: {movie['title']}")
        response = requests.get(movie['link'], headers=self.headers)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            # Fetch genre and description
            genre, parent_div = self._fetch_genre(soup)
            description = self._fetch_description(soup, parent_div if genre != "Genre not found" else None)

            # Fetch production
            countries, year = self._fetch_production(soup)

            # Update movie details with genre, description, and production
            self.movies[movie['title']].update({
                "genre": genre,
                "description": description,
                "countries": countries,
                "year": year
            })

            # Save the movie to the database with the new production info
            movie_id = self.db.save_movie(movie['title'], genre, description, year, countries)
            self.logger.info(f"Fetched details for: {movie['title']}")
            # Save the movie screening times in the db
            screenings = movie.get("screenings", {})
            self.db.save_screenings(movie_id, screenings)
        else:
            self.logger.error(f"Failed to fetch movie page for {movie['title']}. Status code: {response.status_code}")

    def _get_movies_schedule(self) -> Dict[str, Dict[str, Union[str, Dict[str, List[str]]]]]:
        """Private method to get the movie schedule."""
        for date in self._get_dates_range():
            self._parse_movies(date)

        for movie in self.movies.values():
            self._fetch_movie_details(movie)

        return self.movies

    def get_movies(self) -> Dict[str, Dict[str, Union[str, Dict[str, List[str]]]]]:
        """Public method to get the movie schedule."""
        return self._get_movies_schedule()

    def send_new_movies_email(self) -> None:
        """Send an email with the new movies collected."""

        # Collect all new movies
        new_movies = [
            {
                'title': movie['title'],
                'link': movie.get('link', 'Not available'),
                'genre': movie.get('genre', 'Not available'),
                'description': movie.get('description', 'Not available'),
                'production_year': movie.get('year', 'Unknown'),
                'screening_times': [{'date': date, 'times': times} for date, times in movie['screenings'].items()]
            }
            for movie in self.movies.values()
        ]

        # If we have new movies, send an email
        if new_movies:
            email_sender = EmailSender()
            email_sender.send_email(new_movies)

    def close_db(self) -> None:
        """Close the database connection."""
        self.db.close()


def main() -> None:
    scraper = KinoScraper()

    # Get the movie schedule for tomorrow
    movies_list = scraper.get_movies()

    # Send an email with new movies
    scraper.send_new_movies_email()

    # Log the collected movie details
    movies_list_json = json.dumps(movies_list, indent=4, ensure_ascii=False)
    scraper.movies_logger.info("Collected movie details:\n%s", movies_list_json)

    # Close the database connection after processing
    scraper.close_db()


if __name__ == "__main__":
    main()
