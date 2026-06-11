import streamlit as st
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────
# SHARED STORAGE
# ─────────────────────────────────────────────────────────────────────
STORAGE_FILE = "fifa2026_predictions.json"
DEADLINE = "Wednesday EOD"
DEADLINE_DATE = datetime(2026, 6, 15, 23, 59, 59)
SUBMISSIONS_OPEN = datetime.now() < DEADLINE_DATE

# ─────────────────────────────────────────────────────────────────────
# TOURNAMENT MODE  ← switch to "2026" when the tournament begins
# ─────────────────────────────────────────────────────────────────────
TOURNAMENT_YEAR = "2026"   # "2022" for testing | "2026" for live

# ─────────────────────────────────────────────────────────────────────
# GROUP DATA
# ─────────────────────────────────────────────────────────────────────
GROUPS_2026 = {
    "A": sorted(["South Africa", "South Korea", "Mexico", "Czechia"]),
    "B": sorted(["Switzerland", "Canada", "Qatar", "Bosnia and Herzegovina"]),
    "C": sorted(["Brazil", "Morocco", "Haiti", "Scotland"]),
    "D": sorted(["Australia", "Paraguay", "Türkiye", "USA"]),
    "E": sorted(["Curacao", "Ecuador", "Germany", "Ivory Coast"]),
    "F": sorted(["Japan", "Netherlands", "Sweden", "Tunisia"]),
    "G": sorted(["Belgium", "Egypt", "Iran", "New Zealand"]),
    "H": sorted(["Cape Verde", "Saudi Arabia", "Spain", "Uruguay"]),
    "I": sorted(["France", "Iraq", "Norway", "Senegal"]),
    "J": sorted(["Algeria", "Argentina", "Austria", "Jordan"]),
    "K": sorted(["Colombia", "DR Congo", "Portugal", "Uzbekistan"]),
    "L": sorted(["Croatia", "England", "Ghana", "Panama"]),
}

BEST_THIRD_POOL_2026 = sorted([
    "Algeria", "Argentina", "Australia", "Austria", "Belgium",
    "Bosnia and Herzegovina", "Brazil", "Canada", "Cape Verde",
    "Colombia", "Croatia", "Curacao", "Czechia", "DR Congo",
    "Ecuador", "Egypt", "England", "France", "Germany", "Ghana",
    "Haiti", "Iran", "Iraq", "Ivory Coast", "Japan", "Jordan",
    "Mexico", "Morocco", "Netherlands", "New Zealand", "Norway",
    "Panama", "Paraguay", "Portugal", "Qatar", "Saudi Arabia",
    "Scotland", "Senegal", "South Africa", "South Korea", "Spain",
    "Sweden", "Switzerland", "Tunisia", "Türkiye", "United States",
    "Uruguay", "Uzbekistan",
])

# 2022 had 8 groups (A–H), no "best third" — top 2 per group advanced
GROUPS_2022 = {
    "A": sorted(["Qatar", "Ecuador", "Senegal", "Netherlands"]),
    "B": sorted(["England", "Iran", "USA", "Wales"]),
    "C": sorted(["Argentina", "Saudi Arabia", "Mexico", "Poland"]),
    "D": sorted(["France", "Australia", "Denmark", "Tunisia"]),
    "E": sorted(["Spain", "Costa Rica", "Germany", "Japan"]),
    "F": sorted(["Belgium", "Canada", "Morocco", "Croatia"]),
    "G": sorted(["Brazil", "Serbia", "Switzerland", "Cameroon"]),
    "H": sorted(["Portugal", "Ghana", "Uruguay", "South Korea"]),
}

GROUP_ALIAS = {"USA": "United States"}
CURRENT_PHASE = "phase1"

PHASE_POINTS = {
    "phase1_top32":     1,
    "phase2_top16":     2,
    "phase3_quarters":  4,
    "phase4_semis":     8,
    "phase5_finalists": 16,
    "phase6_winner":    32,
}

# Wikipedia group URLs per tournament
WIKI_GROUP_URLS = {
    "2022": {
        g: f"https://en.wikipedia.org/wiki/2022_FIFA_World_Cup_Group_{g}"
        for g in "ABCDEFGH"
    },
    "2026": {
        g: f"https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_Group_{g}"
        for g in "ABCDEFGHIJKL"
    },
}

WIKI_KNOCKOUT_URL = {
    "2022": "https://en.wikipedia.org/wiki/2022_FIFA_World_Cup_knockout_stage",
    "2026": "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}

# ─────────────────────────────────────────────────────────────────────
# STORAGE
# ─────────────────────────────────────────────────────────────────────
def load_predictions() -> dict:
    if Path(STORAGE_FILE).exists():
        with open(STORAGE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_prediction(payload: dict) -> None:
    data = load_predictions()

    email_key = payload["email"].strip().lower()

    if email_key not in data:
        data[email_key] = {
            "name": payload["name"],
            "email": payload["email"],
            "submissions": {}
        }

    data[email_key]["submissions"][CURRENT_PHASE] = {
        **payload,
        "submitted_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    with open(STORAGE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ─────────────────────────────────────────────────────────────────────
# SCRAPERS
# ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def scrape_group_qualifiers(year: str) -> dict:
    """
    Scrapes Wikipedia group pages for `year` and returns:
      { "A": ["Team1","Team2"], "B": [...], ... }
    Also returns the FULL table per group for display.
    Returns: (qualifiers_dict, table_dict)
      qualifiers_dict: {group: [t1, t2]}
      table_dict:      {group: [{"pos":1,"team":"X","pld":3,"w":2,...}, ...]}
    """
    qualifiers = {}
    tables = {}

    for grp, url in WIKI_GROUP_URLS[year].items():
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            for table in soup.find_all("table", class_="wikitable"):
                raw_headers = [th.get_text(strip=True).lower()
                               for th in table.find_all("th")]
                if "pos" in raw_headers and "pts" in raw_headers and "pld" in raw_headers:
                    rows = table.find_all("tr")[1:]
                    top2 = []
                    full_table = []
                    for row in rows:
                        cells = row.find_all(["td", "th"])
                        if len(cells) < 9:
                            continue
                        # pos | team | pld | w | d | l | gf | ga | gd | pts
                        def cell_text(c):
                            return c.get_text(strip=True).split("[")[0].strip()

                        pos_text = cell_text(cells[0])
                        if not pos_text.isdigit():
                            continue

                        link = cells[1].find("a")
                        team = (link.get_text(strip=True) if link
                                else cell_text(cells[1]))
                        team = team.split("[")[0].strip()

                        row_data = {
                            "pos":  int(pos_text),
                            "team": team,
                            "pld":  cell_text(cells[2]),
                            "w":    cell_text(cells[3]),
                            "d":    cell_text(cells[4]),
                            "l":    cell_text(cells[5]),
                            "gf":   cell_text(cells[6]),
                            "ga":   cell_text(cells[7]),
                            "gd":   cell_text(cells[8]),
                            "pts":  cell_text(cells[9]) if len(cells) > 9 else "—",
                        }
                        full_table.append(row_data)
                        if len(top2) < 2 and team:
                            top2.append(team)

                    if top2:
                        qualifiers[grp] = top2
                        tables[grp] = full_table
                    break

        except Exception:
            continue

    return qualifiers, tables


@st.cache_data(ttl=300)
def scrape_knockout_stage(year: str) -> dict:
    """
    Returns:
    {
      "round_of_16":  set of team names | None,
      "quarters":     set | None,
      "semis":        set | None,
      "finalists":    set | None,
      "winner":       str | None,
      "round_tables": {round_label: [{"team1":..,"team2":..,"score":..}, ...]}
    }
    """
    result = {
        "round_of_16":  None,
        "quarters":     None,
        "semis":        None,
        "finalists":    None,
        "winner":       None,
        "round_tables": {},
    }

    try:
        resp = requests.get(WIKI_KNOCKOUT_URL[year], headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        round_map = [
            ("round of 16",   "round_of_16"),
            ("round of 32",   "round_of_16"),   # 2026 uses R32
            ("quarter-final", "quarters"),
            ("quarterfinal",  "quarters"),
            ("semi-final",    "semis"),
            ("semifinal",     "semis"),
        ]

        for heading in soup.find_all(["h2", "h3"]):
            heading_text = heading.get_text(strip=True).lower()

            # Skip "third place" headings
            if "third" in heading_text:
                continue

            matched_key = None
            for keyword, key in round_map:
                if keyword in heading_text:
                    matched_key = key
                    break

            # Final detection
            is_final = (
                "final" in heading_text
                and "semi" not in heading_text
                and "third" not in heading_text
                and "quarter" not in heading_text
            )

            if not matched_key and not is_final:
                continue

            teams = set()
            for sibling in heading.find_all_next(["table", "div", "h2", "h3"]):
                if sibling.name in ["h2", "h3"] and sibling != heading:
                    break
                for link in sibling.find_all("a"):
                    title = link.get("title", "")
                    text  = link.get_text(strip=True).split("[")[0].strip()
                    if (
                        ("national football team" in title.lower()
                         or "national soccer team" in title.lower())
                        and text
                    ):
                        teams.add(text)

            if is_final and teams:
                result["finalists"] = teams
                # Try to find the winner (bold / "champion" tag near the heading)
                for sib in heading.find_all_next(["table", "div"]):
                    for b_tag in sib.find_all(["b", "strong"]):
                        candidate = b_tag.get_text(strip=True).split("[")[0].strip()
                        if candidate in teams:
                            result["winner"] = candidate
                            break
                    if result["winner"]:
                        break
            elif matched_key and teams:
                result[matched_key] = teams

    except Exception:
        pass

    return result


# ─────────────────────────────────────────────────────────────────────
# SCORE CALCULATOR
# ─────────────────────────────────────────────────────────────────────
def norm(s: str) -> str:
    return s.lower().strip()

def count_matches(predicted: list, actual) -> int:
    if not actual:
        return 0
    actual_norm = {norm(t) for t in actual}
    return sum(1 for t in predicted if norm(t) in actual_norm)

def calculate_scores(predictions: dict, year: str) -> tuple[dict, dict, dict]:
    """
    Returns (scores, actual_results, group_tables)
    actual_results: {phase_label: set_of_teams_or_str}
    """
    group_q, group_tables = scrape_group_qualifiers(year)
    knockout = scrape_knockout_stage(year)

    actual_top32 = {t for teams in group_q.values() for t in teams} if group_q else set()

    actual_results = {}
    if actual_top32:
        actual_results["Phase 1 – Top 32 / Group Qualifiers"] = actual_top32
    if knockout["round_of_16"]:
        actual_results["Phase 2 – Round of 16"] = knockout["round_of_16"]
    if knockout["quarters"]:
        actual_results["Phase 3 – Quarter-finals"] = knockout["quarters"]
    if knockout["semis"]:
        actual_results["Phase 4 – Semi-finals"] = knockout["semis"]
    if knockout["finalists"]:
        actual_results["Phase 5 – Finalists"] = knockout["finalists"]
    if knockout["winner"]:
        actual_results["Phase 6 – Winner"] = {knockout["winner"]}

    scores = {}
    for name, entry in predictions.items():
        breakdown = {}
        total = 0

        if actual_top32:
            predicted = entry.get("top_32", [])
            pts = count_matches(predicted, actual_top32) * PHASE_POINTS["phase1_top32"]
            breakdown["Phase 1 – Top 32 (×1)"] = (pts, count_matches(predicted, actual_top32), len(actual_top32))
            total += pts

        if knockout["round_of_16"]:
            predicted = entry.get("phase2_top16", [])
            m = count_matches(predicted, knockout["round_of_16"])
            pts = m * PHASE_POINTS["phase2_top16"]
            breakdown["Phase 2 – Round of 16 (×2)"] = (pts, m, len(knockout["round_of_16"]))
            total += pts

        if knockout["quarters"]:
            predicted = entry.get("phase3_quarters", [])
            m = count_matches(predicted, knockout["quarters"])
            pts = m * PHASE_POINTS["phase3_quarters"]
            breakdown["Phase 3 – Quarters (×4)"] = (pts, m, len(knockout["quarters"]))
            total += pts

        if knockout["semis"]:
            predicted = entry.get("phase4_semis", [])
            m = count_matches(predicted, knockout["semis"])
            pts = m * PHASE_POINTS["phase4_semis"]
            breakdown["Phase 4 – Semis (×8)"] = (pts, m, len(knockout["semis"]))
            total += pts

        if knockout["finalists"]:
            predicted = entry.get("phase5_finalists", [])
            m = count_matches(predicted, knockout["finalists"])
            pts = m * PHASE_POINTS["phase5_finalists"]
            breakdown["Phase 5 – Finalists (×16)"] = (pts, m, len(knockout["finalists"]))
            total += pts

        if knockout["winner"]:
            predicted_w = entry.get("phase6_winner", "")
            hit = int(norm(predicted_w) == norm(knockout["winner"]))
            pts = hit * PHASE_POINTS["phase6_winner"]
            breakdown[f"Phase 6 – Winner: {knockout['winner']} (×32)"] = (pts, hit, 1)
            total += pts

        scores[name] = {"total": total, "breakdown": breakdown}

    return scores, actual_results, group_tables


# ─────────────────────────────────────────────────────────────────────
# PAGE CONFIG & CSS
# ─────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FIFA Prediction Game",
    page_icon="🏆",
    layout="wide"
)
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: linear-gradient(160deg,#0a1f0a 0%,#0d2b0d 55%,#091a09 100%); color:#e8f5e9; }
.hero { text-align:center; padding:2.4rem 1rem 1.4rem; border-bottom:2px solid #2e7d32; margin-bottom:1.8rem; }
.hero h1 { font-family:'Bebas Neue',sans-serif; font-size:3rem; letter-spacing:0.08em; color:#ffd600; line-height:1.1; margin:0 0 0.3rem; text-shadow:0 2px 16px rgba(255,214,0,.28); }
.hero .sub { font-size:.9rem; color:#81c784; letter-spacing:.14em; text-transform:uppercase; font-weight:600; }
.info-row { display:flex; gap:.8rem; margin-bottom:1.6rem; flex-wrap:wrap; }
.info-card { flex:1; min-width:110px; background:rgba(46,125,50,.15); border:1px solid #2e7d32; border-radius:10px; padding:.9rem .6rem; text-align:center; }
.ic-icon { font-size:1.4rem; }
.ic-label { font-size:.65rem; text-transform:uppercase; letter-spacing:.1em; color:#81c784; margin-top:.25rem; }
.ic-val { font-size:1rem; font-weight:700; color:#ffd600; margin-top:.15rem; }
.deadline-strip { background:rgba(255,214,0,.08); border:1px solid #ffd600; border-radius:8px; padding:.65rem 1rem; font-size:.85rem; color:#ffd600; margin-bottom:1.4rem; text-align:center; }
.sec-head { font-family:'Bebas Neue',sans-serif; font-size:1.6rem; letter-spacing:.07em; color:#ffd600; border-left:4px solid #43a047; padding-left:.7rem; margin:2rem 0 .6rem; }
.sec-sub { font-size:.78rem; color:#81c784; margin:-.4rem 0 1rem 1rem; letter-spacing:.05em; }
.prog-wrap { background:#1b5e20; border-radius:20px; height:8px; margin:.5rem 0 .3rem; overflow:hidden; }
.prog-fill { height:100%; background:linear-gradient(90deg,#43a047,#ffd600); border-radius:20px; }
.prog-label { font-size:.75rem; color:#a5d6a7; text-align:right; }
div.stButton > button { background:linear-gradient(135deg,#ffd600,#ffab00) !important; color:#0a1f0a !important; font-family:'Bebas Neue',sans-serif !important; font-size:1.3rem !important; letter-spacing:.1em !important; border:none !important; border-radius:8px !important; padding:.6rem 2.5rem !important; width:100% !important; margin-top:1rem !important; }
.success-box { background:rgba(27,94,32,.5); border:1px solid #43a047; border-radius:10px; padding:1.2rem 1.5rem; margin-top:1rem; color:#c8e6c9; text-align:center; }
.score-row { display:flex; justify-content:space-between; align-items:center; padding:.5rem .8rem; border-bottom:1px solid rgba(46,125,50,.3); }
.score-rank { font-family:'Bebas Neue',sans-serif; font-size:1.2rem; color:#ffd600; width:2.5rem; }
.score-name { flex:1; font-weight:600; color:#e8f5e9; }
.score-pts { font-family:'Bebas Neue',sans-serif; font-size:1.3rem; color:#43a047; }
.used-tag { display:inline-block; padding:2px 8px; font-size:.72rem; background:rgba(255,255,255,.07); color:#555; border-radius:4px; text-decoration:line-through; margin:2px; }
.phase2 { margin-top:2.5rem; padding:1.2rem; background:rgba(255,214,0,.06); border:1px dashed #ffd600; border-radius:10px; text-align:center; }
.test-banner { background:rgba(255,152,0,.12); border:1px solid #ff9800; border-radius:8px; padding:.7rem 1rem; font-size:.85rem; color:#ffcc80; margin-bottom:1rem; text-align:center; }
/* Comparison table */
.cmp-table { width:100%; border-collapse:collapse; font-size:.82rem; margin-top:.5rem; }
.cmp-table th { background:#1b5e20; color:#a5d6a7; padding:.4rem .6rem; text-align:left; font-weight:600; letter-spacing:.05em; }
.cmp-table td { padding:.35rem .6rem; border-bottom:1px solid rgba(46,125,50,.25); }
.cmp-table tr.hit td { background:rgba(67,160,71,.18); color:#c8e6c9; }
.cmp-table tr.miss td { background:rgba(229,57,53,.08); color:#ef9a9a; }
.tag-hit { display:inline-block; background:#1b5e20; color:#a5d6a7; border-radius:4px; padding:1px 7px; font-size:.75rem; }
.tag-miss { display:inline-block; background:rgba(229,57,53,.15); color:#ef9a9a; border-radius:4px; padding:1px 7px; font-size:.75rem; }
label { color:#a5d6a7 !important; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────
# ACTIVE GROUPS & POOL
# ─────────────────────────────────────────────────────────────────────
GROUPS = GROUPS_2022 if TOURNAMENT_YEAR == "2022" else GROUPS_2026
HAS_BEST_THIRD = (TOURNAMENT_YEAR == "2026")
BEST_THIRD_POOL = BEST_THIRD_POOL_2026 if HAS_BEST_THIRD else []

predictions_db = load_predictions()
scores = {}
actual_results = {}
group_tables = {}

if not SUBMISSIONS_OPEN:

    try:
        scores, actual_results, group_tables = calculate_scores(
            predictions_db,
            TOURNAMENT_YEAR
        )

    except Exception:
        pass
if "play_game" not in st.session_state:
    st.session_state.play_game = False
if "submitted" not in st.session_state:
    st.session_state.submitted = False
# ─────────────────────────────────────────────────────────────────────
# HERO
# ─────────────────────────────────────────────────────────────────────
year_label = "2022 (Test Mode)" if TOURNAMENT_YEAR == "2022" else "2026"

st.markdown(f"""
<div class="hero">
  <div class="sub">⚽ LT Prediction Challenge</div>
  <h1>FIFA {year_label}<br>Prediction Game</h1>
  <div class="sub">Phase 1 — Top {"16 (Group Qualifiers)" if TOURNAMENT_YEAR == "2022" else "32 Qualified Teams"}</div>
</div>
<div class="info-row">
  <div class="info-card"><div class="ic-icon">🏆</div><div class="ic-label">Phase</div><div class="ic-val">1 of 6</div></div>
  <div class="info-card"><div class="ic-icon">🎯</div><div class="ic-label">Phase 1 Pts</div><div class="ic-val">1/team</div></div>
  <div class="info-card"><div class="ic-icon">📈</div><div class="ic-label">Multiplier</div><div class="ic-val">×2/phase</div></div>
  <div class="info-card"><div class="ic-icon">👥</div><div class="ic-label">Submitted</div><div class="ic-val">{len(predictions_db)}</div></div>
  <div class="info-card"><div class="ic-icon">⏰</div><div class="ic-label">Deadline</div><div class="ic-val">{DEADLINE}</div></div>
</div>
<div class="deadline-strip">⏰ &nbsp;<strong>Deadline:</strong> {DEADLINE} — Predictions lock once matches begin. All picks stay confidential until then.</div>
""", unsafe_allow_html=True)

if TOURNAMENT_YEAR == "2022":
    st.markdown("""
    <div class="test-banner">
      🧪 <strong>TEST MODE — Using FIFA 2022 (Qatar) data.</strong>
      All results are already known. Change <code>TOURNAMENT_YEAR = "2026"</code> to go live.
    </div>
    """, unsafe_allow_html=True)

with st.expander("📋 Scoring Rules"):
    st.markdown("""
| Phase | Stage | Points per correct team |
|---|---|---|
| 1 | Top qualifiers (Group stage) | **1 pt** |
| 2 | Round of 16 | **2 pts** |
| 3 | Quarterfinals | **4 pts** |
| 4 | Semifinals | **8 pts** |
| 5 | Finalists | **16 pts** |
| 6 | Winner | **32 pts** |

*Scores fetched live from Wikipedia via BeautifulSoup — refreshed every 5 minutes.*
    """)

# ─────────────────────────────────────────────────────────────────────
# SUBMISSION FORM
# ─────────────────────────────────────────────────────────────────────
if not st.session_state.play_game:

    st.markdown(
        """
        <div style='text-align:center;padding:2rem'>
        <h2>Ready to Predict?</h2>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.button("🎮 Play The Game"):
        st.session_state.play_game = True
        st.rerun()
if st.session_state.play_game and not st.session_state.submitted:
    left_col, right_col = st.columns([3, 1])
    with left_col:
        st.markdown('<div class="sec-head">Your Details</div>', unsafe_allow_html=True)
        name = st.text_input(
            "Your Name *",
            placeholder="e.g. John Doe"
        )

        email = st.text_input(
            "Email Address *",
            placeholder="e.g. johndoe@gmail.com"
        )

        st.markdown(f'<div class="sec-head">Groups {"A – H" if TOURNAMENT_YEAR == "2022" else "A – L"}</div>', unsafe_allow_html=True)
        st.markdown('<div class="sec-sub">Pick the 2 teams you think will qualify from each group</div>', unsafe_allow_html=True)

        group_picks = {}
        groups_complete = 0
        group_keys = list(GROUPS.keys())

        for i in range(0, len(group_keys), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                if i + j >= len(group_keys):
                    break
                gk = group_keys[i + j]
                with col:
                    picks = st.multiselect(
                        f"**Group {gk}**",
                        options=GROUPS[gk],
                        max_selections=2,
                        key=f"group_{gk}",
                        placeholder="Pick 2 teams…",
                    )
                    group_picks[gk] = picks
                    count = len(picks)
                    color = "#ffd600" if count == 2 else "#ef5350" if count > 2 else "#43a047"
                    st.markdown(
                        f'<div class="prog-wrap"><div class="prog-fill" style="width:{count/2*100}%"></div></div>'
                        f'<div class="prog-label" style="color:{color}">{count}/2</div>',
                        unsafe_allow_html=True,
                    )
                    if count == 2:
                        groups_complete += 1

        # Best Third (2026 only)
        if HAS_BEST_THIRD:
            st.markdown('<div class="sec-head">Best Third Place</div>', unsafe_allow_html=True)
            st.markdown('<div class="sec-sub">Select 8 third-placed teams you think will advance</div>', unsafe_allow_html=True)

            already_picked: set[str] = set()
            for picks in group_picks.values():
                for p in picks:
                    already_picked.add(p)
                    if p in GROUP_ALIAS:
                        already_picked.add(GROUP_ALIAS[p])

            available_third = [t for t in BEST_THIRD_POOL if t not in already_picked]
            locked_third    = [t for t in BEST_THIRD_POOL if t in already_picked]

            if locked_third:
                greyed = " ".join(f'<span class="used-tag">{t}</span>' for t in sorted(locked_third))
                st.markdown(
                    f'<div style="margin-bottom:.8rem"><span style="font-size:.74rem;color:#555">🔒 ALREADY PICKED IN GROUPS:</span><br>{greyed}</div>',
                    unsafe_allow_html=True,
                )

            best_third = st.multiselect(
                "Best third-place teams (pick 8)",
                options=available_third,
                max_selections=8,
                placeholder="Search or scroll…",
                key="best_third",
            )
            bt_count = len(best_third)
            bt_color = "#ffd600" if bt_count == 8 else "#ef5350" if bt_count > 8 else "#43a047"
            st.markdown(
                f'<div class="prog-wrap"><div class="prog-fill" style="width:{bt_count/8*100}%"></div></div>'
                f'<div class="prog-label" style="color:{bt_color}">{bt_count}/8</div>',
                unsafe_allow_html=True,
            )
        else:
            best_third = []
            bt_count   = 0

        # Overall progress
        total_picked = sum(len(v) for v in group_picks.values()) + bt_count
        max_teams = 32 if HAS_BEST_THIRD else len(group_keys) * 2
        st.markdown(f"""
        <div style="margin:1.5rem 0 .5rem;padding:1rem;background:rgba(46,125,50,.12);border:1px solid #2e7d32;border-radius:10px;">
          <div style="font-size:.8rem;color:#81c784;text-transform:uppercase;letter-spacing:.08em;margin-bottom:.5rem">Overall Progress</div>
          <div class="prog-wrap"><div class="prog-fill" style="width:{min(total_picked/max_teams*100,100)}%"></div></div>
          <div style="display:flex;justify-content:space-between;font-size:.8rem;margin-top:.3rem;">
            <span style="color:#a5d6a7">Groups complete: <strong style="color:#ffd600">{groups_complete}/{len(group_keys)}</strong></span>
            <span style="color:#a5d6a7">Teams picked: <strong style="color:#ffd600">{total_picked}/{max_teams}</strong></span>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # Submit
        st.markdown('<div class="sec-head" style="font-size:1.2rem">Lock In Your Prediction</div>', unsafe_allow_html=True)

        if st.button("⚽  Submit My Prediction"):
            errors = []
            if not name.strip():
                errors.append("Please enter your name.")
            if not email.strip():
                errors.append("Please enter your email.")
            incomplete = [gk for gk, p in group_picks.items() if len(p) != 2]
            if incomplete:
                errors.append(f"Pick exactly 2 teams from each group. Incomplete: Group {', '.join(incomplete)}.")
            if HAS_BEST_THIRD and bt_count != 8:
                errors.append(f"Select exactly 8 best third-place teams (you have {bt_count}).")
            email_key = email.strip().lower()

            if email_key in predictions_db:

                existing_submissions = predictions_db[email_key].get(
                    "submissions",
                    {}
                )

                if CURRENT_PHASE in existing_submissions:
                    errors.append(
                        f"You have already submitted for {CURRENT_PHASE}"
                    )

            if errors:
                for e in errors:
                    st.error(e)
            else:
                all_top = [t for gk in group_keys for t in group_picks[gk]] + best_third
                email_key = email.strip().lower()

                if email_key in predictions_db:
                    existing_phase = predictions_db[email_key].get("phase")

                    if existing_phase == CURRENT_PHASE:
                        errors.append(
                            f"This email has already submitted for {CURRENT_PHASE}."
                        )
                save_prediction({
                    "name": name.strip(),
                    "email": email.strip().lower(),
                    "groups": group_picks,
                    "best_third": best_third,
                    "top_32": all_top,
                })

                st.session_state.submitted = True

                st.markdown(f"""
                <div class="success-box">
                  <div style="font-size:2rem">🎉</div>
                  <div style="font-size:1.2rem;font-weight:700;color:#ffd600;margin:.4rem 0">
                    Prediction Locked!
                  </div>
                  <div>
                    Thanks <strong>{name.strip()}</strong> — your picks are saved and confidential.
                  </div>
                  <div style="font-size:.82rem;margin-top:.5rem;color:#81c784">
                    Results will be shared once predictions close. Good luck! 🍀
                  </div>
                </div>
                """, unsafe_allow_html=True)

                st.balloons()

                st.rerun()
    with right_col:

        st.markdown("### 🏆 Leaderboard")

        if scores:
            ranked = sorted(
                scores.items(),
                key=lambda x: x[1]["total"],
                reverse=True
            )

            for rank, (email, data) in enumerate(ranked, start=1):

                player_name = predictions_db[email]["name"]

                medal = ""
                if rank == 1:
                    medal = "🥇"
                elif rank == 2:
                    medal = "🥈"
                elif rank == 3:
                    medal = "🥉"

                st.markdown(
                    f"**{medal} {player_name}**  \n"
                    f"{data['total']} pts"
                )

        else:
            # Tournament not started yet
            for record in predictions_db.values():
                st.markdown(
                    f"""
                    <div class="score-row">
                        <div class="score-name">{record['name']}</div>
                        <div class="score-pts">0 pts</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
# if st.session_state.submitted:
#
#     st.success("✅ Your prediction has been submitted successfully.")
#
#     st.markdown("## 👥 Participants")
#
#     for record in predictions_db.values():
#         st.write(f"• {record['name']}")
c1, c2, c3 = st.columns([1, 2, 1])
with c2:

    st.markdown(
        "<h2 style='text-align:center;'>👥 Participants</h2>",
        unsafe_allow_html=True
    )

    for record in predictions_db.values():

        st.markdown(
            f"""
            <div class="score-row">
                <div class="score-name">{record['name']}</div>
                <div class="score-pts">0 pts</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

# ─────────────────────────────────────────────────────────────────────
# LEADERBOARD & COMPARISON
# ─────────────────────────────────────────────────────────────────────
# st.markdown("---")
# st.markdown('<div class="sec-head" style="font-size:1.1rem">🏅 Leaderboard & Results</div>', unsafe_allow_html=True)

predictions_db = load_predictions()
scores = {}
if predictions_db:
    col1, col2 = st.columns([3, 1])
    # with col1:
    #     st.markdown(
    #         f'<div style="background:rgba(46,125,50,.15);border:1px solid #2e7d32;border-radius:8px;'
    #         f'padding:.6rem 1rem;font-size:.9rem;color:#a5d6a7;">'
    #         f'🌍 &nbsp;<strong style="color:#ffd600">{len(predictions_db)}</strong> participant(s) have submitted</div>',
    #         unsafe_allow_html=True,
    #     )
    with col2:
        if st.button("🔄 Refresh"):
            scrape_group_qualifiers.clear()
            scrape_knockout_stage.clear()
            st.rerun()

    # with st.expander("👥 Who has submitted (picks hidden 🔒)"):
    #     for i, (pname, entry) in enumerate(predictions_db.items(), 1):
    #         ts = entry.get("submitted_at", "")
    #         st.markdown(f"**{i}.** {pname} &nbsp;—&nbsp; <span style='color:#81c784;font-size:.8rem'>{ts}</span>", unsafe_allow_html=True)

    with st.spinner("Scraping latest results from Wikipedia…"):
        scores, actual_results, group_tables = calculate_scores(predictions_db, TOURNAMENT_YEAR)

    # ── ACTUAL RESULTS PANEL ──────────────────────────────────────────
    if actual_results:
        st.markdown('<div class="sec-head" style="font-size:1rem">📋 Actual Results (from Wikipedia)</div>', unsafe_allow_html=True)

        # Group standings
        if group_tables:
            with st.expander("📊 Group Stage Standings (scraped)"):
                for grp, rows in sorted(group_tables.items()):
                    st.markdown(f"**Group {grp}**")
                    tbl_html = """
                    <table class="cmp-table">
                      <tr><th>Pos</th><th>Team</th><th>Pld</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th></tr>
                    """
                    for row in rows:
                        highlight = ' style="background:rgba(67,160,71,.15);"' if row["pos"] <= 2 else ""
                        tbl_html += (
                            f'<tr{highlight}><td>{row["pos"]}</td><td><strong>{row["team"]}</strong></td>'
                            f'<td>{row["pld"]}</td><td>{row["w"]}</td><td>{row["d"]}</td><td>{row["l"]}</td>'
                            f'<td>{row["gf"]}</td><td>{row["ga"]}</td><td>{row["gd"]}</td><td>{row["pts"]}</td></tr>'
                        )
                    tbl_html += "</table>"
                    st.markdown(tbl_html, unsafe_allow_html=True)
                    st.markdown("")

        # Knockout actual teams
        for phase_label, team_set in actual_results.items():
            if phase_label == "Phase 1 – Top 32 / Group Qualifiers":
                continue   # already in group standings above
            with st.expander(f"🏟 {phase_label} — {len(team_set)} team(s)"):
                teams_sorted = sorted(team_set)
                cols = st.columns(3)
                for idx, t in enumerate(teams_sorted):
                    cols[idx % 3].markdown(f"⚽ {t}")

    # ── LEADERBOARD ───────────────────────────────────────────────────
    if any(s["total"] > 0 for s in scores.values()):
        ranked = sorted(scores.items(), key=lambda x: x[1]["total"], reverse=True)
        st.markdown('<div class="sec-head" style="font-size:1rem">📊 Current Scores</div>', unsafe_allow_html=True)

        for rank, (pname, data) in enumerate(ranked, 1):
            medal = ["🥇","🥈","🥉"][rank-1] if rank <= 3 else f"{rank}."
            st.markdown(
                f'<div class="score-row">'
                f'<div class="score-rank">{medal}</div>'
                f'<div class="score-name">{pname}</div>'
                f'<div class="score-pts">{data["total"]} pts</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── DETAILED COMPARISON per person ────────────────────────────
        st.markdown('<div class="sec-head" style="font-size:1rem">🔍 Prediction vs Actual</div>', unsafe_allow_html=True)

        for pname, data in ranked:
            entry = predictions_db[pname]
            with st.expander(f"📂 {pname} — {data['total']} pts"):
                for phase_label, (pts, hits, total_actual) in data["breakdown"].items():
                    # Get the predicted list for this phase
                    if "Top 32" in phase_label or "Top 16" in phase_label:
                        predicted = entry.get("top_32", [])
                        actual_set = actual_results.get("Phase 1 – Top 32 / Group Qualifiers", set())
                    elif "Round of 16" in phase_label:
                        predicted = entry.get("phase2_top16", [])
                        actual_set = actual_results.get("Phase 2 – Round of 16", set())
                    elif "Quarter" in phase_label:
                        predicted = entry.get("phase3_quarters", [])
                        actual_set = actual_results.get("Phase 3 – Quarter-finals", set())
                    elif "Semi" in phase_label:
                        predicted = entry.get("phase4_semis", [])
                        actual_set = actual_results.get("Phase 4 – Semi-finals", set())
                    elif "Finalist" in phase_label:
                        predicted = entry.get("phase5_finalists", [])
                        actual_set = actual_results.get("Phase 5 – Finalists", set())
                    elif "Winner" in phase_label:
                        predicted = [entry.get("phase6_winner", "")]
                        actual_set = actual_results.get("Phase 6 – Winner", set())
                    else:
                        predicted = []
                        actual_set = set()

                    st.markdown(
                        f"**{phase_label}** &nbsp;—&nbsp; "
                        f"<span style='color:#ffd600'>{pts} pts</span> "
                        f"<span style='color:#81c784;font-size:.8rem'>({hits}/{total_actual} correct)</span>",
                        unsafe_allow_html=True,
                    )

                    if predicted and actual_set:
                        actual_norm_set = {norm(t) for t in actual_set}
                        predicted_norm  = {norm(t) for t in predicted}

                        # Deduplicate actual for display
                        all_teams = sorted(set(list(predicted) + list(actual_set)))

                        tbl = '<table class="cmp-table"><tr><th>Team</th><th>You Predicted</th><th>Actually Qualified</th></tr>'
                        for team in sorted(actual_set):
                            you_picked = norm(team) in predicted_norm
                            row_class  = "hit" if you_picked else "miss"
                            you_tag    = '<span class="tag-hit">✓ Picked</span>' if you_picked else '<span class="tag-miss">✗ Missed</span>'
                            tbl += f'<tr class="{row_class}"><td><strong>{team}</strong></td><td>{you_tag}</td><td><span class="tag-hit">✓</span></td></tr>'

                        # Teams you picked but did NOT qualify
                        for team in sorted(predicted):
                            if team and norm(team) not in actual_norm_set:
                                tbl += f'<tr class="miss"><td><strong>{team}</strong></td><td><span class="tag-hit">✓ Picked</span></td><td><span class="tag-miss">✗ Did not qualify</span></td></tr>'

                        tbl += "</table>"
                        st.markdown(tbl, unsafe_allow_html=True)
                    st.markdown("")

    else:
        st.info("Scores will appear here once match data is available on Wikipedia.")

else:
    st.info("No submissions yet. Be the first! ⚽")

st.markdown("""
<div class="phase2">
  <div style="font-family:'Bebas Neue',sans-serif;font-size:1.4rem;color:#ffd600;letter-spacing:.08em">🔜 Phase 2 Coming Soon</div>
  <div style="font-size:.85rem;color:#a5d6a7;margin-top:.4rem">
    Top 16 · Quarterfinals · Semifinals · Finalists · Winner<br>
    <strong style="color:#ffd600">Points double each round — 1 → 2 → 4 → 8 → 16 → 32</strong>
  </div>
</div>
""", unsafe_allow_html=True)