"""College football reference data for draft prospect relationships."""

import re


# ESPN college-football team IDs, not school-name slugs, identify CDN logos.
ESPN_TEAM_IDS = {
    "boston-college": "103", "california": "25", "clemson": "228", "duke": "150",
    "florida-state": "52", "georgia-tech": "59", "louisville": "97", "miami": "2390",
    "nc-state": "152", "north-carolina": "153", "notre-dame": "87", "pittsburgh": "221",
    "smu": "2567", "stanford": "24", "syracuse": "183", "virginia": "258",
    "virginia-tech": "259", "wake-forest": "154", "illinois": "356", "indiana": "84",
    "iowa": "2294", "maryland": "120", "michigan": "130", "michigan-state": "127",
    "minnesota": "135", "nebraska": "158", "northwestern": "77", "ohio-state": "194",
    "oregon": "2483", "penn-state": "213", "purdue": "2509", "rutgers": "164",
    "ucla": "26", "usc": "30", "washington": "264", "wisconsin": "275",
    "arizona": "12", "arizona-state": "9", "baylor": "239", "byu": "252",
    "cincinnati": "2132", "colorado": "38", "houston": "248", "iowa-state": "66",
    "kansas": "2305", "kansas-state": "2306", "oklahoma-state": "197", "tcu": "2628",
    "texas-tech": "2641", "ucf": "2116", "utah": "254", "west-virginia": "277",
    "alabama": "333", "arkansas": "8", "auburn": "2", "florida": "57",
    "georgia": "61", "kentucky": "96", "lsu": "99", "mississippi-state": "344",
    "missouri": "142", "oklahoma": "201", "ole-miss": "145", "south-carolina": "2579",
    "tennessee": "2633", "texas": "251", "texas-a-m": "245", "vanderbilt": "238",
    "army": "349", "charlotte": "2429", "east-carolina": "151", "florida-atlantic": "2226",
    "memphis": "235", "navy": "2426", "north-texas": "249", "rice": "242",
    "temple": "218", "tulane": "2655", "tulsa": "202", "uab": "5",
    "south-florida": "58", "utsa": "2636", "appalachian-state": "2026", "arkansas-state": "2032",
    "coastal-carolina": "324", "georgia-southern": "290", "georgia-state": "2247", "james-madison": "256",
    "louisiana": "309", "louisiana-monroe": "2433", "marshall": "276", "old-dominion": "295",
    "south-alabama": "6", "southern-miss": "2572", "texas-state": "326", "troy": "2653",
    "air-force": "2005", "boise-state": "68", "colorado-state": "36", "fresno-state": "278",
    "hawaii": "62", "nevada": "2440", "new-mexico": "167", "san-diego-state": "21",
    "san-jose-state": "23", "unlv": "2439", "utah-state": "328", "wyoming": "2751",
    "delaware": "48", "florida-international": "2229", "jacksonville-state": "55", "kennesaw-state": "338",
    "liberty": "2335", "louisiana-tech": "2348", "middle-tennessee": "2393", "missouri-state": "2623",
    "new-mexico-state": "166", "sam-houston": "2534", "utep": "2638", "western-kentucky": "98",
    "akron": "2006", "ball-state": "2050", "bowling-green": "189", "buffalo": "2084",
    "central-michigan": "2117", "eastern-michigan": "2199", "kent-state": "2309", "miami-ohio": "193",
    "northern-illinois": "2459", "ohio": "195", "toledo": "2649", "umass": "113",
    "western-michigan": "2711", "oregon-state": "204", "washington-state": "265", "connecticut": "41",
    "youngstown-state": "2754",
}


def college_logo_url(college_id: str, stored_url: str) -> str:
    """Resolve legacy seeded URLs without replacing custom college artwork."""
    legacy_url = f"https://a.espncdn.com/i/teamlogos/ncaa/500/{college_id}.png"
    team_id = ESPN_TEAM_IDS.get(college_id)
    if team_id is not None and stored_url in ("", legacy_url):
        return f"https://a.espncdn.com/i/teamlogos/ncaa/500/{team_id}.png"
    return stored_url


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
                "logo_url": college_logo_url(slug, ""),
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
) + (
    {
        "id": "youngstown-state",
        "name": "Youngstown State",
        "abbreviation": "youngstown-state",
        "conference": "Missouri Valley Football Conference",
        "division": "FCS",
        "logo_url": college_logo_url("youngstown-state", ""),
        "official_url": "https://ysusports.com/sports/football",
    },
)