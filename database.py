import sqlite3
import logging
from typing import Optional, List, Tuple, Dict


class Database:
    def __init__(self, db_name: str = "movies.db") -> None:
        self.db_name: str = db_name
        self.conn: Optional[sqlite3.Connection] = None
        self.cursor: Optional[sqlite3.Cursor] = None
        self.logger: logging.Logger = logging.getLogger(__name__)

    def connect(self) -> None:
        """Establish a connection to the database."""
        try:
            self.conn = sqlite3.connect(
                f"file:{self.db_name}?mode=rw&cache=shared",  # Enable shared cache
                uri=True,  # Use URI mode
                check_same_thread=False  # Allow multiple threads to use the connection
            )
            self.cursor = self.conn.cursor()
            self.logger.info(f"Connected to database: {self.db_name} (shared cache mode enabled)")
        except sqlite3.Error as e:
            self.logger.error(f"Error connecting to database: {e}")
            raise

    def initialize_schema(self) -> None:
        """Create tables if they don't exist."""
        schema_statements = [
            '''
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                genre TEXT,
                description TEXT,
                year INTEGER,
                countries TEXT,
                firstly_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(title, year)  -- Ensure uniqueness based on title and year
            )
            ''',
            '''
            CREATE TABLE IF NOT EXISTS screenings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                movie_id INTEGER,  -- Foreign key referencing the movies table
                screening_date TEXT,  -- example: "2025-02-01"
                screening_time TEXT,  -- example: "14:00", "18:30", etc.
                FOREIGN KEY(movie_id) REFERENCES movies(id),
                UNIQUE(movie_id, screening_date, screening_time)  -- Ensure uniqueness for each movie and screening time
            )
            '''
        ]
        try:
            for statement in schema_statements:
                self.cursor.execute(statement)
            self.conn.commit()
            self.logger.info("Database schema initialized.")
        except sqlite3.Error as e:
            self.logger.error(f"Error initializing schema: {e}")
            raise

    def _update_movie(self, movie_id: int, genre: str, description: str, countries: str) -> None:
        """Update movie details in the database."""
        self.cursor.execute('''
            UPDATE movies
            SET genre = ?, description = ?, countries = ?, last_updated = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (genre, description, countries, movie_id))

    def _insert_movie(self, title: str, genre: str, description: str, year: int, countries: str) -> int:
        """Insert a new movie into the database."""
        self.cursor.execute('''
            INSERT INTO movies (title, genre, description, year, countries, firstly_added)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (title, genre, description, year, countries))
        return self.cursor.lastrowid

    def save_movie(self, title: str, genre: str, description: str, year: int, countries: str) -> Optional[int]:
        """Save movie details to the database."""
        try:
            self.cursor.execute("SELECT id FROM movies WHERE title = ? AND year = ?", (title, year))
            movie = self.cursor.fetchone()

            if movie:
                movie_id = movie[0]
                self._update_movie(movie_id, genre, description, countries)
                self.logger.info(f"Updated existing movie: {title} ({year})")
            else:
                movie_id = self._insert_movie(title, genre, description, year, countries)
                self.logger.info(f"Inserted new movie: {title} ({year})")

            self.conn.commit()
            return movie_id
        except sqlite3.Error as e:
            self.logger.error(f"Error saving movie {title} ({year}): {e}")
            return None

    def save_screenings(self, movie_id: int, screenings: Dict[str, List[str]]) -> None:
        """Save movie screenings to the database."""
        if not movie_id:
            self.logger.error(f"Invalid movie ID: {movie_id}")
            return

        try:
            for screening_date, screening_times in screenings.items():
                for screening_time in screening_times:
                    self.cursor.execute('''
                        INSERT OR IGNORE INTO screenings (movie_id, screening_date, screening_time)
                        VALUES (?, ?, ?)
                    ''', (movie_id, screening_date, screening_time))

            self.conn.commit()
            self.logger.info(f"Screenings saved for movie ID {movie_id}")
        except sqlite3.Error as e:
            self.logger.error(f"Error saving screenings for movie ID {movie_id}: {e}")

    def fetch_movie_titles_and_years(self) -> List[Tuple[str, int]]:
        """Retrieve movie title and production year from the database."""
        try:
            self.cursor.execute("SELECT title, year FROM movies")
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            self.logger.error(f"Error fetching movies: {e}")
            return []

    def close(self) -> None:
        """Close the database connection."""
        if self.conn:
            self.conn.close()
            self.logger.info("Database connection closed.")
