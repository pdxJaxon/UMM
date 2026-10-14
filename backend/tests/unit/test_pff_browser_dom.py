"""Exercise the actual DOM extraction script in Chromium, without network access."""

from pathlib import Path

import pytest
from playwright.sync_api import Error, sync_playwright

from app.services.pff_browser_collector import EXTRACT_BOARD, snapshot_from_rendered


@pytest.fixture
def page():
    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).exists():
            pytest.skip("Chromium is not installed; run python -m playwright install chromium")
        browser = playwright.chromium.launch()
        try:
            yield browser.new_page()
        finally:
            browser.close()


def _html(grade_markup: str) -> str:
    return f"""<main>
      <h1>BIG BOARD 2027</h1><p>Updated - Oct 6, 2026 11:59 am EDT</p>
      <div class="m-player-row" data-player-id="source-123">
        <span class="m-player-row__rank-value">1</span>
        <button class="m-player-row__name">Test Runner Jr.<svg></svg></button>
        <span class="m-player-row__position">HB</span>
        <span class="m-player-row__college">Ohio State</span>
        {grade_markup}
      </div>
    </main>"""


@pytest.mark.parametrize("grade", [None, 0, 94.5])
def test_real_dom_extraction_preserves_missing_and_zero_grades(page, grade):
    markup = "" if grade is None else f'<span class="kyber-grade-badge__info-text">{grade}</span>'
    page.set_content(_html(markup))
    extracted = page.locator("main").evaluate(EXTRACT_BOARD)
    snapshot = snapshot_from_rendered(extracted, 2027)
    assert snapshot.prospects[0].pff_grade == grade
    assert snapshot.prospects[0].name == "Test Runner Jr."
    assert snapshot.prospects[0].source_record_id == "source-123"
    assert snapshot.source_updated_at_display == "Oct 6, 2026 11:59 am EDT"


def test_non_numeric_grade_is_not_silently_converted_to_missing(page):
    page.set_content(_html('<span class="kyber-grade-badge__info-text">unavailable?</span>'))
    with pytest.raises(Error, match="non-numeric"):
        page.locator("main").evaluate(EXTRACT_BOARD)
