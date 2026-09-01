"""Pure HTML parsers for kinonh.pl. No network or database I/O."""

from __future__ import annotations

import re
from typing import List, Optional, TypedDict
from urllib.parse import urljoin

from bs4 import BeautifulSoup

SCREENING_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
EXTERNAL_ID_RE = re.compile(r"(?:[?&]id=|/id/)(\d+)", re.IGNORECASE)

REQUIRED_REPERTORY_MARKERS = ("pastyt", "tyt", "seanserep")
REQUIRED_DETAIL_MARKERS = ("gatunek", "produkcja:")


class Listing(TypedDict):
    title: str
    link: str
    external_id: Optional[str]
    times: List[str]


class MovieDetails(TypedDict):
    genre: str
    description: str
    countries: str
    year: str


def extract_external_id(href: str) -> Optional[str]:
    if not href:
        return None
    match = EXTERNAL_ID_RE.search(href)
    return match.group(1) if match else None


def movie_key(listing: Listing) -> str:
    return listing["external_id"] or listing["title"]


def parse_screening_times(times_div) -> List[str]:
    """Collect HH:MM times from a seanserep block, including sold-out/inactive slots."""
    if times_div is None:
        return []
    times: List[str] = []
    seen = set()
    for anchor in times_div.find_all("a"):
        text = anchor.get_text(strip=True)
        if SCREENING_TIME_RE.match(text) and text not in seen:
            seen.add(text)
            times.append(text)
    return times


def parse_repertory_html(raw_html: str, base_url: str) -> List[Listing]:
    """Parse the HTML fragment stored in rep.json['lista']."""
    if not raw_html:
        return []

    soup = BeautifulSoup(raw_html, "html.parser")
    listings: List[Listing] = []

    for event in soup.find_all("div", class_="pastyt"):
        title_tag = event.find("a", class_="tyt")
        if not title_tag:
            continue
        href = title_tag.get("href") or ""
        title = title_tag.get_text(strip=True)
        if not title:
            continue
        times_div = event.find_next_sibling("div", class_="seanserep")
        listings.append(
            {
                "title": title,
                "link": urljoin(base_url, href),
                "external_id": extract_external_id(href),
                "times": parse_screening_times(times_div),
            }
        )
    return listings


def clean_genre_text(genre_text: str) -> str:
    if "gatunek:" in genre_text:
        genre_text = genre_text.split("gatunek:", 1)[1].strip()
    if "kategoria wiekowa:" in genre_text:
        genre_text = genre_text.split("kategoria wiekowa:", 1)[0].strip()
    if "czas trwania:" in genre_text:
        genre_text = genre_text.split("czas trwania:", 1)[0].strip()
    return genre_text


def clean_production_text(production_text: str) -> tuple[str, str]:
    if "produkcja:" in production_text.lower():
        production_text = re.sub(r"(?i)produkcja:", "", production_text).strip()

    year_match = re.search(r"(\d{4})$", production_text)
    year = year_match.group(1) if year_match else "Unknown"
    countries = production_text[: year_match.start()].strip() if year_match else production_text
    return countries, year


def parse_genre(soup: BeautifulSoup) -> tuple[str, Optional[object]]:
    genre_h4 = next((h4 for h4 in soup.find_all("h4") if "gatunek" in h4.get_text().lower()), None)
    if genre_h4:
        return clean_genre_text(genre_h4.get_text().strip()), genre_h4.find_parent()
    return "Genre not found", None


def parse_description(soup: BeautifulSoup, parent_div=None) -> str:
    if parent_div:
        paragraphs = [p.get_text(" ", strip=True) for p in parent_div.find_all("p") if p.get_text(strip=True)]
        if paragraphs:
            return "\n".join(paragraphs)
    description_h4 = next((h4 for h4 in soup.find_all("h4") if "opis" in h4.get_text().lower()), None)
    if description_h4:
        parent = description_h4.find_parent()
        if parent:
            paragraphs = [p.get_text(" ", strip=True) for p in parent.find_all("p") if p.get_text(strip=True)]
            if paragraphs:
                return "\n".join(paragraphs)
    return "Description not found"


def parse_production(soup: BeautifulSoup) -> tuple[str, str]:
    for div in soup.find_all("div", class_="f4 crrow"):
        if "produkcja:" in div.get_text().lower():
            return clean_production_text(div.get_text(strip=True))
    return "Unknown", "Unknown"


def parse_movie_details(html: bytes | str) -> MovieDetails:
    soup = BeautifulSoup(html, "html.parser")
    genre, parent_div = parse_genre(soup)
    description = parse_description(soup, parent_div if genre != "Genre not found" else None)
    countries, year = parse_production(soup)
    return {
        "genre": genre,
        "description": description,
        "countries": countries,
        "year": year,
    }


def repertory_contract_issues(lista_html: str) -> List[str]:
    issues: List[str] = []
    if not lista_html or not str(lista_html).strip():
        return ["rep.json 'lista' is empty"]
    text = str(lista_html)
    for marker in REQUIRED_REPERTORY_MARKERS:
        if marker not in text:
            issues.append(f"missing repertory marker: {marker}")
    if "pastyt" in text and not BeautifulSoup(text, "html.parser").find_all("div", class_="pastyt"):
        issues.append("pastyt marker present but no div.pastyt nodes parsed")
    return issues


def movie_page_contract_issues(html: str) -> List[str]:
    issues: List[str] = []
    lowered = html.lower()
    for marker in REQUIRED_DETAIL_MARKERS:
        if marker not in lowered:
            issues.append(f"missing movie-page marker: {marker}")
    return issues
