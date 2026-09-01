import sqlite3
import logging
from typing import Dict, List, Optional, Tuple


class Database:
    def __init__(self, db_name: str = "movies.db") -> None:
        self.db_name: str = db_name
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None
        self.logger: logging.Logger = logging.getLogger(__name__)

    def connect(self) -> None:
        """Establish a connection to the database, creating the file if needed."""
        try:
            self.conn = sqlite3.connect(self.db_name, check_same_thread=False)
            self.conn.execute("PRAGMA foreign_keys = ON")
            self.cursor = self.conn.cursor()
            self.logger.info("Connected to database: %s", self.db_name)
        except sqlite3.Error as e:
            self.logger.error("Error connecting to database: %s", e)
            raise

    def initialize_schema(self) -> None:
        """Create tables if they don't exist and apply lightweight migrations."""
        schema_statements = [
            """
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                genre TEXT,
                description TEXT,
                year TEXT,
                countries TEXT,
                external_id TEXT,
                firstly_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(title, year)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS screenings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movie_id INTEGER,
                screening_date TEXT,
                screening_time TEXT,
                FOREIGN KEY(movie_id) REFERENCES movies(id),
                UNIQUE(movie_id, screening_date, screening_time)
            )
            """,
        ]
        try:
            for statement in schema_statements:
                self.cursor.execute(statement)
            self._ensure_column("movies", "external_id", "TEXT")
            self.cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_movies_external_id "
                "ON movies(external_id) WHERE external_id IS NOT NULL AND external_id != ''"
            )
            self.conn.commit()
            self.logger.info("Database schema initialized.")
        except sqlite3.Error as e:
            self.logger.error("Error initializing schema: %s", e)
            raise

    def _ensure_column(self, table: str, column: str, definition: str) -> None:
        existing = {row[1] for row in self.cursor.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            self.cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            self.logger.info("Added column %s.%s", table, column)

    def _update_movie(
        self,
        movie_id: int,
        genre: str,
        description: str,
        countries: str,
        external_id: Optional[str] = None,
    ) -> None:
        self.cursor.execute(
            """
            UPDATE movies
            SET genre = ?, description = ?, countries = ?, last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (genre, description, countries, movie_id),
        )
        if external_id:
            self.cursor.execute(
                "UPDATE movies SET external_id = COALESCE(NULLIF(external_id, ''), ?) WHERE id = ?",
                (external_id, movie_id),
            )

    def _insert_movie(
        self,
        title: str,
        genre: str,
        description: str,
        year: str,
        countries: str,
        external_id: Optional[str] = None,
    ) -> int:
        self.cursor.execute(
            """
            INSERT INTO movies (title, genre, description, year, countries, external_id, firstly_added)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (title, genre, description, year, countries, external_id),
        )
        return self.cursor.lastrowid

    def _find_movie_id(self, title: str, year: str, external_id: Optional[str]) -> Optional[int]:
        if external_id:
            row = self.cursor.execute(
                "SELECT id FROM movies WHERE external_id = ?", (external_id,)
            ).fetchone()
            if row:
                return row[0]
        row = self.cursor.execute(
            "SELECT id FROM movies WHERE title = ? AND year = ?", (title, year)
        ).fetchone()
        return row[0] if row else None

    def save_movie(
        self,
        title: str,
        genre: str,
        description: str,
        year: str,
        countries: str,
        external_id: Optional[str] = None,
    ) -> Optional[int]:
        """Save movie details to the database."""
        try:
            movie_id = self._find_movie_id(title, year, external_id)
            if movie_id:
                self._update_movie(movie_id, genre, description, countries, external_id)
                self.logger.info("Updated existing movie: %s (%s)", title, year)
            else:
                movie_id = self._insert_movie(title, genre, description, year, countries, external_id)
                self.logger.info("Inserted new movie: %s (%s)", title, year)
            self.conn.commit()
            return movie_id
        except sqlite3.Error as e:
            self.logger.error("Error saving movie %s (%s): %s", title, year, e)
            return None

    def save_screenings(self, movie_id: int, screenings: Dict[str, List[str]]) -> None:
        """Save movie screenings to the database."""
        if not movie_id:
            self.logger.error("Invalid movie ID: %s", movie_id)
            return

        try:
            for screening_date, screening_times in screenings.items():
                for screening_time in screening_times:
                    self.cursor.execute(
                        """
                        INSERT OR IGNORE INTO screenings (movie_id, screening_date, screening_time)
                        VALUES (?, ?, ?)
                        """,
                        (movie_id, screening_date, screening_time),
                    )
            self.conn.commit()
            self.logger.info("Screenings saved for movie ID %s", movie_id)
        except sqlite3.Error as e:
            self.logger.error("Error saving screenings for movie ID %s: %s", movie_id, e)

    def fetch_known_movies(self) -> Tuple[Dict[str, int], Dict[str, int]]:
        """Return (external_id -> id, title -> id) maps of movies already stored."""
        by_external_id: Dict[str, int] = {}
        by_title: Dict[str, int] = {}
        try:
            self.cursor.execute("SELECT id, title, external_id FROM movies")
            for movie_id, title, external_id in self.cursor.fetchall():
                if title:
                    by_title[title] = movie_id
                if external_id:
                    by_external_id[str(external_id)] = movie_id
            return by_external_id, by_title
        except sqlite3.Error as e:
            self.logger.error("Error fetching movies: %s", e)
            return {}, {}

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None
            self.cursor = None
            self.logger.info("Database connection closed.")
