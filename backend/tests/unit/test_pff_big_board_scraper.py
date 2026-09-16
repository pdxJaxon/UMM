"""Tests for structured PFF Big Board scraping."""

from unittest.mock import Mock

from app.services.pff_big_board_scraper import PFFBigBoardScraper


def test_scraper_parses_embedded_big_board_json() -> None:
    """Embedded application JSON should become normalized prospect records."""
    html = '<script type="application/json">{"players":[{"id":7,"name":"Test Prospect","position":"WR","college":"alabama","rank":1}]}</script>'
    records = PFFBigBoardScraper.parse_html(html, 2027)

    assert records[0]["id"] == "7"
    assert records[0]["first_name"] == "Test"
    assert records[0]["pff_rank"] == 1


def test_scraper_fetches_season_and_sends_optional_bearer_key() -> None:
    """The page request should include the requested season and optional API key."""
    response = Mock()
    response.text = '<script type="application/json">{"players":[{"id":7,"name":"Test Prospect","position":"WR","college":"alabama"}]}</script>'
    client = Mock()
    client.get.return_value = response
    scraper = PFFBigBoardScraper("https://www.pff.com/draft/big-board", "local-key", client=client)

    assert scraper.fetch(2027)[0]["position"] == "WR"
    client.get.assert_called_once_with(
        "https://www.pff.com/draft/big-board",
        params={"season": 2027},
        headers={"Accept": "text/html,application/xhtml+xml", "User-Agent": "UMockMe-prospect-import/1.0", "Authorization": "Bearer local-key"},
    )