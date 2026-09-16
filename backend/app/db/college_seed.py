"""FBS college football reference data for draft prospect relationships."""

import re


def _slug(name: str) -> str:
    """Create a stable URL-safe identifier from a school name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _records(conference: str, names: tuple[str, ...]) -> tuple[dict[str, str], ...]:
    """Create normalized FBS records for one conference."""
    records = []
    for name in names:
        slug = _slug(name)
        records.append(
            {
                "id": slug,
                "name": name,
                "abbreviation": slug[:20],
                "conference": conference,
                "division": "FBS",
                "logo_url": f"https://a.espncdn.com/i/teamlogos/ncaa/500/{slug}.png",
                "official_url": f"https://www.ncaa.com/schools/{slug}",
            }
        )
    return tuple(records)


COLLEGES = tuple(
    record
    for conference, names in (
        ("ACC", ("Boston College", "California", "Clemson", "Duke", "Florida State", "Georgia Tech", "Louisville", "Miami", "NC State", "North Carolina", "Notre Dame", "Pittsburgh", "SMU", "Stanford", "Syracuse", "Virginia", "Virginia Tech", "Wake Forest")),
        ("Big Ten", ("Illinois", "Indiana", "Iowa", "Maryland", "Michigan", "Michigan State", "Minnesota", "Nebraska", "Northwestern", "Ohio State", "Oregon", "Penn State", "Purdue", "Rutgers", "UCLA", "USC", "Washington", "Wisconsin")),
        ("Big 12", ("Arizona", "Arizona State", "Baylor", "BYU", "Cincinnati", "Colorado", "Houston", "Iowa State", "Kansas", "Kansas State", "Oklahoma State", "TCU", "Texas Tech", "UCF", "Utah", "West Virginia")),
        ("SEC", ("Alabama", "Arkansas", "Auburn", "Florida", "Georgia", "Kentucky", "LSU", "Mississippi State", "Missouri", "Oklahoma", "Ole Miss", "South Carolina", "Tennessee", "Texas", "Texas A&M", "Vanderbilt")),
        ("American Athletic Conference", ("Army", "Charlotte", "East Carolina", "Florida Atlantic", "Memphis", "Navy", "North Texas", "Rice", "Temple", "Tulane", "Tulsa", "UAB", "South Florida", "UTSA")),
        ("Sun Belt Conference", ("Appalachian State", "Arkansas State", "Coastal Carolina", "Georgia Southern", "Georgia State", "James Madison", "Louisiana", "Louisiana-Monroe", "Marshall", "Old Dominion", "South Alabama", "Southern Miss", "Texas State", "Troy")),
        ("Mountain West Conference", ("Air Force", "Boise State", "Colorado State", "Fresno State", "Hawaii", "Nevada", "New Mexico", "San Diego State", "San Jose State", "UNLV", "Utah State", "Wyoming")),
        ("Conference USA", ("Delaware", "Florida International", "Jacksonville State", "Kennesaw State", "Liberty", "Louisiana Tech", "Middle Tennessee", "Missouri State", "New Mexico State", "Sam Houston", "UTEP", "Western Kentucky")),
        ("Mid-American Conference", ("Akron", "Ball State", "Bowling Green", "Buffalo", "Central Michigan", "Eastern Michigan", "Kent State", "Miami (Ohio)", "Northern Illinois", "Ohio", "Toledo", "UMass", "Western Michigan")),
        ("Pac-12 Conference", ("Oregon State", "Washington State")),
        ("FBS Independent", ("Connecticut",)),
    )
    for record in _records(conference, names)
)