"""Fills in details for titles added through the app with only a name.

The app can't look anything up itself — a published Artifact runs under a
strict CSP with no outbound network access — so adding a title just records
it with p:true ("pending"). This script does the lookup out of band and
clears that flag.

Per pending item it resolves:
  y  film vs TV        (TMDb search)
  c  genre bucket      (TMDb genres, mapped onto the app's own taxonomy)
  d  one-line synopsis (first sentence of TMDb's overview)
  s  Tomatometer       (OMDb, keyed by the IMDb id TMDb gives us)

Rotten Tomatoes has no public API; OMDb re-publishes the score and is the
only free source for it. Without OMDB_API_KEY the score is left empty
rather than substituted with TMDb's own rating, which is a different
number and would be wrong under a 🍅 label.

Usage:
    export TMDB_BEARER_TOKEN=...   # required
    export OMDB_API_KEY=...        # optional; without it, no 🍅 scores
    python3 enrich_pending.py app_data.json
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TMDB_BASE = "https://api.themoviedb.org/3"
OMDB_BASE = "http://www.omdbapi.com/"
DESC_MAX = 150

# First match wins, so the order is the priority order. Tuned against how
# the hand-curated titles already in the list are shelved: a romcom lands in
# Romance rather than Comedy, a comedy-drama in Comedy rather than Drama.
MOVIE_GENRE_PRIORITY = [
    ("Documentary & Concert Film", {"Documentary"}),
    ("Animation & Family", {"Animation", "Family"}),
    ("Horror", {"Horror"}),
    ("Action & Sci-Fi", {"Science Fiction", "Action", "Adventure", "Fantasy", "War", "Western"}),
    ("Thriller & Crime", {"Crime", "Thriller", "Mystery"}),
    ("Romance", {"Romance"}),
    ("Comedy", {"Comedy"}),
]
MOVIE_GENRE_FALLBACK = "Drama"

TV_GENRE_PRIORITY = [
    ("Reality", {"Reality", "Talk", "News"}),
    ("Sci-Fi", {"Sci-Fi & Fantasy", "Science Fiction", "Fantasy"}),
    ("Thriller & Crime", {"Crime", "Mystery"}),
    ("Comedy", {"Comedy"}),
]
TV_GENRE_FALLBACK = "Drama"


class EnrichError(Exception):
    pass


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise EnrichError(f"401 Unauthorized from {urllib.parse.urlsplit(url).netloc} — check the API key")
        raise EnrichError(f"HTTP {e.code} from {url}")
    except urllib.error.URLError as e:
        raise EnrichError(f"network error contacting {urllib.parse.urlsplit(url).netloc}: {e.reason}")


def tmdb(path, token, params=None):
    url = f"{TMDB_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    return _get_json(url, {"Authorization": f"Bearer {token}", "accept": "application/json"})


def find_best_match(title, token):
    """Returns (media_type, tmdb_id) or None."""
    data = tmdb("/search/multi", token, {"query": title})
    results = [r for r in data.get("results", []) if r.get("media_type") in ("movie", "tv")]
    if not results:
        return None

    def name_of(r):
        return (r.get("title") or r.get("name") or "").strip().lower()

    exact = [r for r in results if name_of(r) == title.strip().lower()]
    pool = exact or results
    best = max(pool, key=lambda r: r.get("popularity") or 0)
    return best["media_type"], best["id"]


def pick_category(media_type, genre_names):
    table = TV_GENRE_PRIORITY if media_type == "tv" else MOVIE_GENRE_PRIORITY
    fallback = TV_GENRE_FALLBACK if media_type == "tv" else MOVIE_GENRE_FALLBACK
    for category, triggers in table:
        if genre_names & triggers:
            return category
    return fallback


def first_sentence(overview):
    text = " ".join((overview or "").split())
    if not text:
        return "No description yet."
    cut = text
    for end in (". ", "! ", "? "):
        idx = text.find(end)
        if idx != -1 and idx + 1 < len(cut):
            cut = text[: idx + 1]
    if len(cut) > DESC_MAX:
        cut = cut[:DESC_MAX].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return cut


def omdb_rt_score(imdb_id, omdb_key):
    if not (imdb_id and omdb_key):
        return None
    url = OMDB_BASE + "?" + urllib.parse.urlencode({"i": imdb_id, "apikey": omdb_key})
    try:
        data = _get_json(url)
    except EnrichError:
        return None
    for rating in data.get("Ratings") or []:
        if rating.get("Source") == "Rotten Tomatoes":
            value = (rating.get("Value") or "").rstrip("%")
            if value.isdigit():
                return int(value)
    return None


PLACEHOLDER_DESCRIPTIONS = {"", "No description yet."}


def needs_enrichment(item):
    """Pending items need everything. Items added through the old form kept
    whatever the form defaulted to, so they need their gaps filled but not
    their deliberate choices overwritten."""
    if item.get("p"):
        return True
    return (
        not item.get("y")
        or not item.get("c")
        or (item.get("d") or "").strip() in PLACEHOLDER_DESCRIPTIONS
        or item.get("s") is None
    )


def enrich_item(item, token, omdb_key):
    match = find_best_match(item["t"], token)
    if not match:
        return False, "no TMDb match"
    media_type, tmdb_id = match

    details = tmdb(f"/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}", token)
    genre_names = {g["name"] for g in details.get("genres") or []}

    if media_type == "tv":
        imdb_id = (tmdb(f"/tv/{tmdb_id}/external_ids", token) or {}).get("imdb_id")
    else:
        imdb_id = details.get("imdb_id")

    was_pending = bool(item.get("p"))
    # Only a pending item gets its type and genre set from scratch; anything
    # already filed keeps where it was filed, and just has its gaps topped up.
    if was_pending or not item.get("y"):
        item["y"] = "tv" if media_type == "tv" else "movie"
    if was_pending or not item.get("c"):
        item["c"] = pick_category(media_type, genre_names)
    if was_pending or (item.get("d") or "").strip() in PLACEHOLDER_DESCRIPTIONS:
        item["d"] = first_sentence(details.get("overview"))
    if item.get("s") is None:
        score = omdb_rt_score(imdb_id, omdb_key)
        if score is not None:
            item["s"] = score

    item.pop("p", None)
    score_note = f" / {item['s']}%" if item.get("s") is not None else " / no RT score"
    return True, f"{item['y']} / {item['c']}{score_note}"


def main():
    if len(sys.argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        sys.exit(1)

    token = os.environ.get("TMDB_BEARER_TOKEN")
    if not token:
        print("Missing TMDB_BEARER_TOKEN environment variable.", file=sys.stderr)
        sys.exit(1)
    omdb_key = os.environ.get("OMDB_API_KEY")
    if not omdb_key:
        print("Note: OMDB_API_KEY not set — titles will be filed without a Tomatometer score.")

    path = Path(sys.argv[1])
    app_data = json.loads(path.read_text())
    items = app_data.get("customItems", [])
    pending = [i for i in items if needs_enrichment(i)]

    if not pending:
        print("Nothing to enrich.")
        return

    failures = []
    for item in pending:
        print(f"  {item['t']}...", end=" ", flush=True)
        try:
            ok, detail = enrich_item(item, token, omdb_key)
        except EnrichError as e:
            print("ERROR:", e)
            sys.exit(1)
        print(detail)
        if not ok:
            failures.append(item["t"])
        time.sleep(0.1)

    path.write_text(json.dumps(app_data, indent=2))
    enriched = len(pending) - len(failures)
    print(f"\nEnriched {enriched} of {len(pending)} pending title(s); wrote {path}")
    if failures:
        print("Still pending (no match found, left for the next run): " + ", ".join(failures))


if __name__ == "__main__":
    main()
