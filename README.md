# The Watchlist

A personal movie & TV watchlist, styled as a ticket-stub program guide.
174 built-in titles, ranked by Rotten Tomatoes score within each genre,
with "mark seen" tracking and a manual add-title form.

**Live app:** https://claude.ai/code/artifact/a8b00614-0566-4323-a57f-3eab6201f7fd

## Features

- Filter by Film/TV, genre, and watched status; free-text search
- Films ranked by Rotten Tomatoes score within each genre; watched titles sink to the bottom
- Manual "add a title" form (name, type, genre, description, RT score, watched)
- Tapping a title searches it on Google
- Watched status and added titles sync across every device that opens the link

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

**⚠️ It reads this repo's committed `ITEMS` array on GitHub, not the live
app above.** Titles added through the "+" button live only in this
Artifact's `customItems` data until this repo's `index.html` is manually
updated and pushed to GitHub — streaming-tracker's automation has no way to
read the live app directly (a GitHub Actions runner isn't logged into
claude.ai). Add titles via the app as usual, but if you want them included
in the streaming brief, ask Claude to sync the live `customItems`/overrides
into this repo's `ITEMS` array and push before the next check — otherwise
the tracker keeps silently checking an ever-more-outdated list. See
streaming-tracker's README for the full explanation.
