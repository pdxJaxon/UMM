"""Browser orchestration tests without external site or login dependencies."""

from unittest.mock import patch

import pytest

from app.services.pff_browser_collector import collect_board


def _rendered():
    return {
        "title": "BIG BOARD 2027",
        "source_updated_at_display": "Oct 6, 2026 11:59 am EDT",
        "prospects": [
            {"overall_rank": 1, "name": "Test Prospect", "position": "WR", "school": "Ohio State", "pff_grade": None},
        ],
    }


@pytest.fixture
def browser_setup():
    with patch("playwright.sync_api.sync_playwright") as runtime:
        playwright = runtime.return_value.__enter__.return_value
        browser = playwright.chromium.launch.return_value
        playwright.chromium.connect_over_cdp.return_value = browser
        context = browser.new_context.return_value
        page = context.new_page.return_value
        page.url = "https://www.pff.com/draft/big-board?season=2027"
        page.goto.return_value.ok = True
        page.reload.return_value.ok = True
        page.locator.return_value.evaluate.return_value = _rendered()
        page.get_by_role.return_value.count.return_value = 0
        browser.contexts = [context]
        context.pages = [page]
        yield playwright, browser, page


def test_collection_is_read_only_and_closes_owned_browser(browser_setup):
    playwright, browser, page = browser_setup
    snapshot = collect_board(2027, min_prospects=1)
    assert len(snapshot.prospects) == 1
    assert snapshot.prospects[0].pff_grade is None
    playwright.chromium.launch.assert_called_once_with(headless=True)
    browser.new_context.assert_called_once_with()
    browser.close.assert_called_once()
    page.goto.assert_called_once()


def test_authorized_session_is_explicit_not_an_api_key(browser_setup, tmp_path):
    _, browser, _ = browser_setup
    state = tmp_path / "authorized-session.json"
    collect_board(2027, 1, storage_state=state, headed=True)
    browser.new_context.assert_called_once_with(storage_state=str(state))


def test_existing_browser_requires_exact_season_tab_and_is_left_open(browser_setup):
    playwright, browser, page = browser_setup
    collect_board(2027, 1, cdp_url="http://127.0.0.1:9222")
    playwright.chromium.connect_over_cdp.assert_called_once_with("http://127.0.0.1:9222")
    playwright.chromium.launch.assert_not_called()
    page.goto.assert_not_called()
    page.reload.assert_not_called()
    browser.new_context.assert_not_called()
    browser.close.assert_not_called()
    page.url = "https://www.pff.com/draft/big-board?season=2026"
    with pytest.raises(ValueError, match="exactly one"):
        collect_board(2027, 1, cdp_url="http://127.0.0.1:9222")


def test_nightly_existing_browser_reloads_before_reading(browser_setup):
    _, browser, page = browser_setup
    collect_board(2027, 1, cdp_url="http://127.0.0.1:9222", refresh_existing=True)
    page.reload.assert_called_once_with(wait_until="domcontentloaded", timeout=60_000)
    browser.close.assert_not_called()


@pytest.mark.parametrize("status", [None, 403])
def test_existing_browser_reload_failure_never_reads_old_rows(browser_setup, status):
    _, browser, page = browser_setup
    if status is None:
        page.reload.return_value = None
    else:
        page.reload.return_value.ok = False
        page.reload.return_value.status = status
    with pytest.raises(RuntimeError, match="reload failed"):
        collect_board(2027, 1, cdp_url="http://127.0.0.1:9222", refresh_existing=True)
    page.locator.assert_not_called()
    browser.close.assert_not_called()


@pytest.mark.parametrize("kwargs", [
    {"draft_year": 2019}, {"draft_year": 2027, "min_prospects": 0},
    {"draft_year": 2027, "cdp_url": "https://remote.example"},
    {"draft_year": 2027, "cdp_url": "http://127.0.0.1:9222", "headed": True},
    {"draft_year": 2027, "refresh_existing": True},
])
def test_invalid_browser_configuration_fails_before_launch(kwargs):
    with pytest.raises(ValueError):
        collect_board(**kwargs)


def test_partial_board_and_enabled_pagination_fail_closed(browser_setup):
    _, browser, page = browser_setup
    with pytest.raises(ValueError, match="Only 1"):
        collect_board(2027, 32)
    page.get_by_role.return_value.count.return_value = 1
    page.get_by_role.return_value.first.is_enabled.return_value = True
    with pytest.raises(RuntimeError, match="another page"):
        collect_board(2027, 1)
    assert browser.close.call_count == 2


def test_http_failure_closes_browser(browser_setup):
    _, browser, page = browser_setup
    page.goto.return_value.ok = False
    page.goto.return_value.status = 403
    with pytest.raises(RuntimeError, match="403"):
        collect_board(2027, 1)
    browser.close.assert_called_once()


def test_unstable_page_never_yields_a_snapshot(browser_setup):
    _, browser, page = browser_setup
    page.locator.return_value.evaluate.side_effect = [
        {**_rendered(), "changing": index} for index in range(20)
    ]
    with pytest.raises(RuntimeError, match="did not stabilize"):
        collect_board(2027, 1)
    browser.close.assert_called_once()
