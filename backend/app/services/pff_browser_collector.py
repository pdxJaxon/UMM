"""Read-only collection of permitted PFF board rows from a rendered browser."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

from app.services.pff_snapshot import PFFBoardSnapshot

EXTRACT_BOARD = r"""main => {
    const title = main.querySelector('h1')?.textContent.trim() || '';
    const updated = main.textContent.match(/Updated\s*-\s*([^\n]*?\b(?:EDT|EST))/i);
    const prospects = [...main.querySelectorAll('.m-player-row')].map(row => {
        const text = selector => row.querySelector(selector)?.textContent.trim() || null;
        const rank = text('.m-player-row__rank-value');
        const grade = text('.kyber-grade-badge__info-text');
        if (grade !== null && !Number.isFinite(Number(grade))) {
            throw new Error('PFF row contains a non-numeric displayed grade');
        }
        return {
            source_record_id: row.getAttribute('data-player-id') || null,
            overall_rank: rank ? Number(rank) : null,
            name: text('.m-player-row__name'),
            position: text('.m-player-row__position'),
            school: text('.m-player-row__college'),
            pff_grade: grade ? Number(grade) : null
        };
    });
    return {title, source_updated_at_display: updated ? updated[1].trim() : null, prospects};
}"""


def snapshot_from_rendered(
    payload: dict[str, Any], draft_year: int, collected_at: datetime | None = None,
) -> PFFBoardSnapshot:
    """Validate extracted DOM facts without relabeling a different year's board."""
    if payload.get("title", "").casefold() != f"big board {draft_year}":
        raise ValueError(f"Rendered heading does not identify Big Board {draft_year}")
    return PFFBoardSnapshot.model_validate({
        "source": "pff-big-board",
        "source_url": f"https://www.pff.com/draft/big-board?season={draft_year}",
        "draft_year": draft_year,
        "collected_at": collected_at or datetime.now(UTC),
        "source_updated_at_display": payload.get("source_updated_at_display"),
        "collection_method": "rendered browser DOM; main board rows only",
        "scope": "All rows currently rendered; completeness beyond this page is not established",
        "grade_definition": "Displayed PFF grade; not an overall rank, athletic score, or UMM score",
        "prospects": payload["prospects"],
    })


def collect_board(
    draft_year: int,
    min_prospects: int = 32,
    storage_state: Path | None = None,
    headed: bool = False,
    cdp_url: str | None = None,
    *,
    refresh_existing: bool = False,
) -> PFFBoardSnapshot:
    """Read ordinary page content; never log in, bypass controls, or use an API key."""
    from playwright.sync_api import sync_playwright

    if not 2020 <= draft_year <= 2100 or min_prospects < 1:
        raise ValueError("Invalid draft year or minimum prospect count")
    if cdp_url and (storage_state is not None or headed):
        raise ValueError("Existing-browser collection cannot also use --storage-state or --headed")
    if refresh_existing and not cdp_url:
        raise ValueError("Refreshing an existing tab requires a CDP connection")
    if cdp_url:
        connection_url = urlparse(cdp_url)
        if connection_url.scheme != "http" or connection_url.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("CDP connection must use a local HTTP debugging endpoint")
    with sync_playwright() as playwright:
        browser = (
            playwright.chromium.connect_over_cdp(cdp_url)
            if cdp_url else playwright.chromium.launch(headless=not headed)
        )
        try:
            if cdp_url:
                pages = [
                    candidate for context in browser.contexts for candidate in context.pages
                    if urlparse(candidate.url).netloc == "www.pff.com"
                    and urlparse(candidate.url).path == "/draft/big-board"
                    and parse_qs(urlparse(candidate.url).query).get("season") == [str(draft_year)]
                ]
                if len(pages) != 1:
                    raise ValueError("Open exactly one matching PFF season tab in the authorized browser")
                page = pages[0]
                if refresh_existing:
                    response = page.reload(wait_until="domcontentloaded", timeout=60_000)
                    if response is None or not response.ok:
                        raise RuntimeError(
                            f"PFF page reload failed: {response.status if response else 'no response'}"
                        )
            else:
                options: dict[str, Any] = {}
                if storage_state is not None:
                    options["storage_state"] = str(storage_state)
                context = browser.new_context(**options)
                page = context.new_page()
                response = page.goto(
                    f"https://www.pff.com/draft/big-board?season={draft_year}",
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )
                if response is None or not response.ok:
                    raise RuntimeError(f"PFF page request failed: {response.status if response else 'no response'}")
            page.wait_for_function(
                "() => document.querySelector('main .m-player-row__name')?.textContent.trim()",
                timeout=30_000,
            )
            previous: dict[str, Any] | None = None
            for _ in range(20):
                payload = page.locator("main").evaluate(EXTRACT_BOARD)
                if payload == previous:
                    break
                previous = payload
                page.wait_for_timeout(500)
            else:
                raise RuntimeError("PFF rendered board did not stabilize; no snapshot saved")
            next_page = page.get_by_role("button", name="Next", exact=True)
            if next_page.count() and next_page.first.is_enabled():
                raise RuntimeError("PFF board has another page; pagination requires review before collection")
            snapshot = snapshot_from_rendered(payload, draft_year)
            if len(snapshot.prospects) < min_prospects:
                raise ValueError(
                    f"Only {len(snapshot.prospects)} PFF prospects rendered; expected at least {min_prospects}. "
                    "Check access and page layout; partial data will not be saved."
                )
            return snapshot
        finally:
            if not cdp_url:
                browser.close()
