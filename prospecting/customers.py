"""Cross-check companies against public case studies on devin.ai/customers."""
import logging
import re

from bs4 import BeautifulSoup

from . import http
from .companies import Company, normalize_name

log = logging.getLogger(__name__)
CUSTOMERS_URL = "https://devin.ai/customers"


def parse_case_studies(body: str) -> dict[str, str]:
    """Parse the customers page (HTML, or the Markdown variant served to non-browser clients).

    Returns {normalized customer name: case study URL}; names come from the card image alt text and the URL slug.
    """
    out: dict[str, str] = {}

    def add(name: str, slug: str = "", link: str = "") -> None:
        if normalize_name(name):
            out.setdefault(normalize_name(name), link or f"https://devin.ai/customers/{slug}")

    # Markdown cards: [![Wayfair](img)](https://devin.ai/customers/wayfair)
    for alt, slug in re.findall(r"\[!\[([^\]]*)\]\([^)]*\)[^\]]*\]\((?:https://devin\.ai)?/customers/([\w-]+)/?\)", body):
        add(alt, slug)
    # Case-study cards that link off-site (e.g. a LinkedIn post) still use a case-studies cover image.
    for alt, link in re.findall(r"\[!\[([^\]]*)\]\([^)]*case-studies[^)]*\)\]\((https?://[^)]+)\)", body):
        add(alt, link=link)
    for slug in re.findall(r"(?:https://devin\.ai)?/customers/([\w-]+)", body):
        add(slug.replace("-", " "), slug)
    if "<a" in body:
        soup = BeautifulSoup(body, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"^(?:https://devin\.ai)?/customers/[\w-]+/?$")):
            slug = a["href"].rstrip("/").rsplit("/", 1)[-1]
            for img in a.find_all("img"):
                add(img.get("alt", ""), slug)
    return out


def fetch_case_studies(url: str = CUSTOMERS_URL) -> dict[str, str]:
    status, body = http.get(url, as_json=False)
    if status != 200 or not body:
        log.warning("Could not fetch %s (status %s); existing_customer_public will be 'unknown'", url, status)
        return {}
    return parse_case_studies(body)


def match_customer(company: Company, case_studies: dict[str, str]) -> str:
    """Return 'yes (<link>)', 'no', or 'unknown' if the page could not be fetched."""
    if not case_studies:
        return "unknown"
    keys = {normalize_name(company.name), normalize_name(company.name).replace(" ", ""), company.domain_stem}
    for name, link in case_studies.items():
        if name in keys or name.replace(" ", "") in keys:
            return f"yes ({link})"
    return "no"
