# The Watchlist

A personal movie & TV watchlist, styled as a ticket-stub program guide.
174 built-in titles, ranked by Rotten Tomatoes score within each genre,
with "mark seen" tracking and a manual add-title form.

**Live app:** https://claude.ai/code/artifact/a8b00614-0566-4323-a57f-3eab6201f7fd

## Features

- Filter by Film/TV, genre, and watched status; free-text search
- Films ranked by Rotten Tomatoes score within each genre; watched titles sink to the bottom
- "Add a title" takes **just the name** — film vs TV, genre, description, and
  Tomatometer are looked up automatically (see below)
- Remove a title with a confirmation step (see below)
- Tapping a title searches it on Google
- Watched status and added titles sync across every device that opens the link

## Adding a title, and where the details come from

The page can't look anything up itself. A published Artifact runs under a
strict CSP with no outbound network access, so there is no way for the app
to call TMDb, Google, or anything else at the moment you add something.

So adding is two-phase:

1. You type a title. It's saved immediately with `p:true` and shown in an
   "Awaiting details" section, visible in both the Film and TV tabs.
2. `enrich_pending.py` runs out of band and fills in the rest:

   | Field | Source |
   |---|---|
   | film vs TV (`y`) | TMDb search |
   | genre (`c`) | TMDb genres, mapped onto this app's own taxonomy |
   | description (`d`) | first sentence of TMDb's overview |
   | Tomatometer (`s`) | OMDb, keyed by the IMDb id TMDb returns |

Rotten Tomatoes has no public API; OMDb re-publishes the score and is the
only free source for it. **Without `OMDB_API_KEY` set, titles are filed with
no 🍅 score** rather than TMDb's own rating, which is a different number and
would be wrong under a Tomatometer label. Free key:
https://www.omdbapi.com/apikey.aspx

Genre mapping is best-effort — a title can land in a defensible but not
ideal bucket. Ask Claude to move it and it'll edit the entry directly.

```bash
export TMDB_BEARER_TOKEN=...
export OMDB_API_KEY=...          # optional; without it, no 🍅 scores
python3 enrich_pending.py app_data.json   # fill in the blanks
python3 sync_customitems.py app_data.json # promote into ITEMS
```

`sync_customitems.py` *promotes*: enriched items move into `ITEMS` and out
of `customItems`. They must never be in both — the app renders
`ITEMS.concat(customItems)`, so anything in both shows up twice. Items that
found no TMDb match stay in `customItems` for the next run rather than being
promoted with no type or genre, which would make them unrenderable.

### This runs automatically — you don't need to do the above by hand

A scheduled task named **watchlist-auto-enrich**, set up in the Claude
desktop app's "Scheduled" sidebar section (or ask Claude), runs weekly and
does exactly the sequence above on its own:

1. Reads the live app's current `app-data`. This has to happen through a
   real, logged-in Claude session — a plain script hitting that URL gets
   back an anonymous loading shell with no data in it, since artifacts are
   private by default. This is the reason the automation has to be a
   Claude session on a schedule, not a plain cron script.
2. Runs `enrich_pending.py`, then `sync_customitems.py`.
3. Publishes the result back to the live artifact.
4. Commits and pushes to this repo.

It only pushes/publishes when it actually enriched something — a run that
finds nothing pending exits quietly, no commit, no notification. It only
runs while the Claude desktop app is open; if your Mac was off when the
weekly time came around, it just runs once on next launch instead — no
titles are lost, just delayed. Ask Claude to enrich on demand anytime you
don't want to wait for the schedule.

**Why not a scheduled cloud job instead of a local one?** Tried first,
doesn't work: a cloud sandbox's network can reach GitHub but is blocked
from reaching `api.themoviedb.org`, so it can do the "read the live app"
half but not the "look up the details" half. Local is the only environment
with both an authenticated session *and* unrestricted outbound network.

> **This is the one machine-dependent piece in the whole system.**
> `watchlist-auto-enrich` only runs while your Mac is on and the Claude
> desktop app is open (or it catches up on next launch). Contrast with
> [streaming-tracker's monthly email](../streaming-tracker/README.md#monthly-email-via-github-actions),
> which runs in GitHub's cloud on its own schedule and fires whether your
> Mac is on, off, or asleep — that was deliberately built cloud-side so it
> wouldn't share this dependency.

## Removing a title

Every card has a small ✕ in its top-right corner, which asks for
confirmation before removing anything — there's no undo, so nothing is
ever deleted from a single tap.

What removal actually does depends on where the title came from:

- **Added through the app:** deleted outright — it's spliced out of
  `customItems` (or out of the promoted block in `ITEMS`, if it had already
  been enriched) and gone for good.
- **One of the 174 built-in titles:** these live inside `appMain`'s own
  source text, which is exactly what gets re-serialized on every save — so
  splicing it out of the array wouldn't work, the source text would still
  list it. It's suppressed by key instead, recorded in a `deleted` array in
  `app-data`. Recoverable (ask Claude), unlike an app-added title.

The dialog tells you which case you're in before you confirm.

## Files

- `index.html` — the entire app; see "How it's built" below
- `enrich_pending.py` — looks up film/TV, genre, description, Tomatometer for pending titles
- `sync_customitems.py` — promotes enriched titles from `customItems` into the committed `ITEMS` array
- `synced_items.json` — the promoted titles' source of truth, so re-running the sync updates in place rather than duplicating
- `set_app_data.py` — **unused.** Built for an earlier attempt at automation (a scheduled *cloud* job) that turned out not to work — see "This runs automatically" above for why, and what replaced it. Left in place only as a record of that dead end; nothing calls it. Safe to delete.

## How it's built

Single self-contained HTML file (`index.html`) — no build step, no server,
no dependencies. It's a Claude Artifact: a static-ish page hosted on
claude.ai that's granted one persistence primitive, the `artifact`
capability, which lets the page rewrite its own stored HTML.

The app's mutable state (watched-status overrides, custom added titles)
lives as a small JSON blob embedded in a `<script type="application/json"
id="app-data">` tag. Everything else — CSS, markup shell, and the
JavaScript logic itself — is wrapped in one `appMain()` function and
embedded as a static string a second time inside itself, so the page can
fully reconstruct and re-publish a complete copy of itself from client-side
JS alone, with no server code of its own. See the comment above
`HEAD_SOURCE`/`BODY_SHELL_SOURCE` in the script for why those are static
strings rather than read from the live DOM.

**Sync model:** there's one canonical document at the link above. Every
device that opens it reads whatever's currently published there. Marking
something watched rebuilds and republishes the *entire* document (CSS, JS,
all 174 records, and the new state) under that same URL; other open tabs
get told to reload to the new version, and a device that opens the link
later just fetches the latest one. It's last-write-wins, not real-time
collaboration — fine for one person, not built to scale to concurrent
editors.

## Local development

Edit `index.html` directly — it's plain HTML/CSS/JS, readable and
editable with any tool. To preview locally:

```bash
python3 -m http.server 8080
# open http://localhost:8080/index.html
```

Note: `window.claude` (the `artifact` capability) only exists inside the
real claude.ai Artifact viewer. Opened locally or via a plain HTTP server,
"mark seen" and "add a title" still update the UI for that session, but
show a "Preview only" toast instead of actually saving — there's nothing
to publish to outside the real hosted environment.

To publish changes to the live link, use the Artifact tool against this
file, passing the existing artifact URL so it updates in place rather than
creating a new one. Since publishing replaces the *entire* document,
always pull the current live state first (the `app-data` JSON) before
republishing code changes, so you don't overwrite watched-status or added
titles that only exist on the live version.

## Related

[streaming-tracker](../streaming-tracker) is a separate tool (including a
monthly GitHub Actions job) that checks this app's title list against TMDb
and the Streaming Availability API for US streaming changes — intentionally
not part of this app, since it needs API keys that can't safely live in
client-side page source.

**It reads this repo's committed `ITEMS` array on GitHub, not the live app
above** — a GitHub Actions runner isn't logged into claude.ai, so it can't
read the live app directly even if it wanted to. `ITEMS` only reflects
titles the **watchlist-auto-enrich** scheduled task (described above) has
already promoted, so streaming-tracker is current as of whenever that last
ran — normally within the week, sooner if you've asked Claude to run it on
demand. If that scheduled task is ever disabled, this reverts to fully
manual and the gap can grow indefinitely with no warning. See
streaming-tracker's README for the full explanation of what it reads and
why.
