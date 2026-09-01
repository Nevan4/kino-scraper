#!/usr/bin/env python3
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from database import Database
from logger_config import configure_logger, configure_movie_logger
from parsers import (
    Listing,
    movie_key,
    movie_page_contract_issues,
    parse_movie_details,
    parse_repertory_html,
    repertory_contract_issues,
)

BASE_URL = "https://www.kinonh.pl/"
REQUEST_TIMEOUT = 20
DETAIL_FETCH_DELAY_S = 0.15

MovieRecord = Dict[str, Union[str, Dict[str, List[str]], bool, None]]


def build_session(user_agent: Optional[str] = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": user_agent
            or (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
    )
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.4,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


class KinoScraper:
    def __init__(
        self,
        base_url: str = BASE_URL,
        db_name: str = "movies.db",
        session: Optional[requests.Session] = None,
        request_timeout: int = REQUEST_TIMEOUT,
        open_db: bool = True,
    ) -> None:
        self.base_url = base_url if base_url.endswith("/") else base_url + "/"
        self.request_timeout = request_timeout
        self._owns_session = session is None
        self.session = session or build_session()
        self.movies: Dict[str, MovieRecord] = {}
        self.logger = configure_logger(
            self.__class__.__name__,
            log_file="kino_scraper.log",
            level=logging.DEBUG,
        )
        self.logger.info("KinoScraper initialized.")
        self.movies_logger = configure_movie_logger(
            f"{self.__class__.__name__}_movies",
            log_file="movies_updated.log",
            level=logging.DEBUG,
        )

        self.db: Optional[Database] = None
        if open_db:
            self.db = Database(db_name)
            self.db.connect()
            self.db.initialize_schema()

    def _get_dates_range(self, days: int) -> List[str]:
        dates = [(datetime.today() + timedelta(days=i)).strftime("%d-%m-%Y") for i in range(days)]
        self.logger.debug("Fetching movies for dates: %s", dates)
        return dates

    def _get(self, url: str) -> Optional[requests.Response]:
        try:
            response = self.session.get(url, timeout=self.request_timeout)
        except requests.RequestException as exc:
            self.logger.error("Request failed for %s: %s", url, exc)
            return None
        if response.status_code != 200:
            self.logger.error("Failed to fetch %s. Status code: %s", url, response.status_code)
            return None
        return response

    def _fetch_movies_page(self, formatted_date: str) -> Optional[str]:
        url = urljoin(self.base_url, f"rep.json?dzien={formatted_date}")
        self.logger.info("Fetching movies page for date: %s", formatted_date)
        response = self._get(url)
        if response is None:
            return None
        try:
            payload = response.json()
        except ValueError:
            self.logger.error("rep.json for %s was not valid JSON", formatted_date)
            return None
        lista = payload.get("lista") or ""
        if not lista:
            self.logger.warning("Empty repertory lista for %s (ok=%s)", formatted_date, payload.get("ok"))
            return ""
        return lista

    def _merge_listing(self, listing: Listing, formatted_date: str, is_new: bool, known_id: Optional[int]) -> None:
        key = movie_key(listing)
        if key not in self.movies:
            self.movies[key] = {
                "title": listing["title"],
                "link": listing["link"],
                "external_id": listing["external_id"],
                "screenings": {},
                "is_new": is_new,
                "db_id": known_id,
            }
        else:
            # Keep new if it appeared as unknown on any day.
            self.movies[key]["is_new"] = bool(self.movies[key].get("is_new")) or is_new
            if known_id and not self.movies[key].get("db_id"):
                self.movies[key]["db_id"] = known_id
        self.movies[key]["screenings"][formatted_date] = listing["times"]
        self.logger.debug("Parsed movie: %s for %s (%s times)", listing["title"], formatted_date, len(listing["times"]))

    def _parse_movies(self, formatted_date: str, by_external_id: Dict[str, int], by_title: Dict[str, int]) -> None:
        raw_html = self._fetch_movies_page(formatted_date)
        if not raw_html:
            self.logger.debug("Cannot fetch the movie page for %s", formatted_date)
            return

        issues = repertory_contract_issues(raw_html)
        if issues:
            self.logger.warning("Repertory markup issues for %s: %s", formatted_date, issues)

        self.logger.info("Parsing movies for %s...", formatted_date)
        for listing in parse_repertory_html(raw_html, self.base_url):
            known_id = None
            if listing["external_id"] and listing["external_id"] in by_external_id:
                known_id = by_external_id[listing["external_id"]]
            elif listing["title"] in by_title:
                known_id = by_title[listing["title"]]
            self._merge_listing(listing, formatted_date, is_new=known_id is None, known_id=known_id)

    def _fetch_movie_details(self, movie: MovieRecord) -> bool:
        title = str(movie["title"])
        self.logger.info("Fetching details for: %s", title)
        response = self._get(str(movie["link"]))
        if response is None:
            return False

        details = parse_movie_details(response.content)
        movie.update(details)
        issues = movie_page_contract_issues(response.text)
        if issues:
            self.logger.warning("Movie page markup issues for %s: %s", title, issues)

        movie_id = self.db.save_movie(
            title,
            details["genre"],
            details["description"],
            details["year"],
            details["countries"],
            external_id=movie.get("external_id"),
        )
        movie["db_id"] = movie_id
        self.logger.info("Fetched details for: %s", title)
        return True

    def _persist_screenings(self, movie: MovieRecord) -> None:
        movie_id = movie.get("db_id")
        if not movie_id:
            self.logger.error("No database id for %s; skipping screenings", movie.get("title"))
            return
        screenings = movie.get("screenings") or {}
        self.db.save_screenings(int(movie_id), screenings)

    def get_movies(self, days: int = 8) -> Dict[str, MovieRecord]:
        if self.db is None:
            raise RuntimeError("Database is not open; create KinoScraper with open_db=True")

        by_external_id, by_title = self.db.fetch_known_movies()
        for date in self._get_dates_range(days):
            self._parse_movies(date, by_external_id, by_title)

        first_new = True
        for movie in self.movies.values():
            if movie.get("is_new"):
                if not first_new:
                    time.sleep(DETAIL_FETCH_DELAY_S)
                first_new = False
                self._fetch_movie_details(movie)
            self._persist_screenings(movie)

        return self.movies

    def new_movies_for_email(self) -> List[Dict]:
        payload = []
        for movie in self.movies.values():
            if not movie.get("is_new"):
                continue
            payload.append(
                {
                    "title": movie["title"],
                    "link": movie.get("link", "Not available"),
                    "genre": movie.get("genre", "Not available"),
                    "description": movie.get("description", "Not available"),
                    "production_year": movie.get("year", "Unknown"),
                    "screening_times": [
                        {"date": date, "times": times} for date, times in movie.get("screenings", {}).items()
                    ],
                }
            )
        return payload

    def send_new_movies_email(self, num_days: int) -> None:
        from email_sender import EmailSender

        new_movies = self.new_movies_for_email()
        if new_movies:
            EmailSender().send_email(new_movies, num_days=num_days)
        else:
            self.logger.info("No new movies to email.")

    def check_site(self, formatted_date: Optional[str] = None) -> List[str]:
        """Fetch one repertory day + one movie page and report markup contract issues."""
        date = formatted_date or datetime.today().strftime("%d-%m-%Y")
        issues: List[str] = []
        lista = self._fetch_movies_page(date)
        if lista is None:
            return [f"Could not fetch repertory JSON for {date}"]
        issues.extend(repertory_contract_issues(lista))
        listings = parse_repertory_html(lista, self.base_url)
        if not listings:
            issues.append("Parser returned zero listings from a fetched lista")
            return issues

        sample = listings[0]
        response = self._get(sample["link"])
        if response is None:
            issues.append(f"Could not fetch movie page: {sample['link']}")
            return issues
        issues.extend(movie_page_contract_issues(response.text))
        details = parse_movie_details(response.content)
        if details["genre"] == "Genre not found":
            issues.append("Genre parser failed on sample movie page")
        if details["year"] == "Unknown" and details["countries"] == "Unknown":
            issues.append("Production parser failed on sample movie page")
        return issues

    def close(self) -> None:
        if self.db:
            self.db.close()
        if self._owns_session:
            self.session.close()

    def close_db(self) -> None:
        self.close()
