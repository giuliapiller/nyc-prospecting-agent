import pytest

from prospecting.classify import is_engineering, is_nyc, likely_hiring_manager


@pytest.mark.parametrize("title,team,expected", [
    ("Senior Software Engineer, Backend", "Engineering", True),
    ("Staff Site Reliability Engineer", "", True),
    ("Engineering Manager, Data Platforms", "Software Engineering", True),
    ("Senior Sales Engineer", "Sales", False),
    ("Technical Support Engineer 2", "", False),
    ("Senior Consulting Engineer", "PS Field Delivery", False),
    ("Senior Product Manager, Platform", "Product", False),
    ("Developer Advocate", "Marketing", False),
    ("Application Engineer", "AMP, APAC Delivery", False),
    ("Senior Forward Deployment Engineer", "App Modernization ENG", False),
    ("Engineering Manager, Customer Tools", "Engineering", True),
    ("Customer Engineering Manager", "Engineering", False),
    ("Customer Engineer", "", False),
])
def test_is_engineering(title, team, expected):
    assert is_engineering(title, team) is expected


def test_is_nyc():
    assert is_nyc("New York, NY")
    assert is_nyc("Remote - US", "NYC Office")
    assert is_nyc("Brooklyn, New York")
    assert not is_nyc("San Francisco, CA", "Remote - US")
    assert not is_nyc("Albany, New York State")


def test_likely_hiring_manager():
    assert likely_hiring_manager("Senior Software Engineer", "Platform Infrastructure") == "Director of Platform Engineering"
    assert likely_hiring_manager("Engineering Manager, Data Platforms", "") == "VP Platform Engineering"
    assert likely_hiring_manager("Director, Engineering", "") == "CTO / SVP Engineering"
    assert likely_hiring_manager("Mainframe Developer", "") == "Director of Core Systems Engineering"
