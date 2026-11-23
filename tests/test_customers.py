from prospecting.companies import Company, normalize_name
from prospecting.customers import match_customer, parse_case_studies

MD = """
[![Wayfair](https://devin.ai/_next/image?url=%2Fassets%2Fimages%2Fcase-studies%2Fwayfair%2Fcover.webp)](https://devin.ai/customers/wayfair)
[![Citi](https://devin.ai/_next/image?url=%2Fassets%2Fimages%2Fcase-studies%2Fciti-ceo%2Fcover.webp)](https://lnkd.in/p/x)
[![Itaú](https://devin.ai/x/case-studies/itau/cover.webp)](https://devin.ai/customers/itau)
"""
HTML = '<a href="/customers/ge-aerospace"><img alt="GE Aerospace" src="x"></a>'


def company(name, site):
    return Company(name, site, "", "")


def test_parse_markdown_and_html():
    md = parse_case_studies(MD)
    assert md["wayfair"] == "https://devin.ai/customers/wayfair"
    assert md["citi"] == "https://lnkd.in/p/x"
    assert md["itau"] == "https://devin.ai/customers/itau"
    assert parse_case_studies(HTML)["ge aerospace"] == "https://devin.ai/customers/ge-aerospace"


def test_match_customer():
    cs = parse_case_studies(MD)
    assert match_customer(company("Wayfair", "wayfair.com"), cs) == "yes (https://devin.ai/customers/wayfair)"
    assert match_customer(company("Etsy", "etsy.com"), cs) == "no"
    assert match_customer(company("Etsy", "etsy.com"), {}) == "unknown"


def test_normalize_name():
    assert normalize_name("The New York Times") == "new york times"
    assert normalize_name("Moody's") == "moodys"
    assert normalize_name("Itaú") == "itau"
