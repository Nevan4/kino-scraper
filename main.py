#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

from email_sender import EmailSender
from scraper import KinoScraper

PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_PREVIEW_PATH = PROJECT_DIR / "temp-email.html"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Kino Nowe Horyzonty repertory.")
    parser.add_argument("--days", type=int, default=8, help="How many days of schedule to fetch (default: 8)")
    parser.add_argument("--db", default="movies.db", help="SQLite database path")
    parser.add_argument(
        "--scrape-only",
        action="store_true",
        help="Collect movies and write the database, but do not send email",
    )
    parser.add_argument(
        "--preview-email",
        nargs="?",
        const=str(DEFAULT_PREVIEW_PATH),
        default=None,
        metavar="FILE",
        help="Write the email HTML to FILE (default: temp-email.html in the project dir) and do not send",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate live site markup (no DB writes, no email) and exit",
    )
    return parser.parse_args()


def run_check() -> int:
    scraper = KinoScraper(open_db=False)
    try:
        issues = scraper.check_site()
    finally:
        scraper.close()
    if issues:
        print("Site markup check failed:")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("Site markup check passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.check:
        return run_check()

    scraper = KinoScraper(db_name=args.db)
    try:
        movies = scraper.get_movies(days=args.days)
        new_movies = scraper.new_movies_for_email()
        if args.preview_email is not None:
            preview_path = Path(args.preview_email)
            if not preview_path.is_absolute():
                preview_path = PROJECT_DIR / preview_path
            EmailSender().write_preview(new_movies, days=args.days, output_path=preview_path)
            print(f"Email preview written to {preview_path} ({len(new_movies)} new movies).")
        elif not args.scrape_only:
            scraper.send_new_movies_email(num_days=args.days)
        movies_list_json = json.dumps(movies, indent=4, ensure_ascii=False, default=str)
        scraper.movies_logger.info("Collected movie details:\n%s", movies_list_json)
        print(f"Collected {len(movies)} movies ({sum(1 for m in movies.values() if m.get('is_new'))} new).")
    finally:
        scraper.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
