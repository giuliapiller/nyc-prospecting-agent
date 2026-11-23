import csv
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_SUFFIXES = {"the", "inc", "corp", "corporation", "group", "company", "co", "llc", "plc", "holdings"}


@dataclass(frozen=True)
class Company:
    name: str
    website: str
    sector: str
    why_on_list: str

    @property
    def domain_stem(self) -> str:
        return self.website.lower().removeprefix("www.").split(".")[0]


def load_companies(path: Path) -> list[Company]:
    with open(path, newline="", encoding="utf-8") as f:
        return [Company(r["company"].strip(), r["website"].strip(), r["sector"].strip(), r["why_on_list"].strip())
                for r in csv.DictReader(f)]


def normalize_name(name: str) -> str:
    """'The New York Times' -> 'new york times'; "Moody's" -> 'moodys'; 'S&P Global' -> 's and p global'."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = name.lower().replace("&", " and ").replace("'", "").replace("\u2019", "")
    tokens = re.sub(r"[^a-z0-9]+", " ", name).split()
    return " ".join(t for t in tokens if t not in _SUFFIXES)
