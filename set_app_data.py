"""Writes an app-data blob into index.html, leaving all other markup alone.

Used by the automatic enrichment routine, which runs in a cloud sandbox with
no push access to this repo. That constraint drives the split:

  - It may NOT promote titles into ITEMS. Promotion only lands in the repo
    via a push, so the next run would clone a repo that never got it, and
    republishing from that clone would drop the title entirely.
  - It MAY rewrite the app-data blob, because that lives in the published
    artifact, which is exactly what the routine republishes.

So the routine enriches items in place inside customItems and calls this;
promotion into ITEMS stays with sync_customitems.py, run from a checkout
that can actually push.

Usage:
    python3 set_app_data.py app_data.json
"""
import json
import re
import sys
from pathlib import Path

INDEX_HTML = Path(__file__).parent / "index.html"
APP_DATA_RE = re.compile(
    r'(<script type="application/json" id="app-data">)(.*?)(</script>)', re.S
)


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 set_app_data.py app_data.json", file=sys.stderr)
        sys.exit(1)

    app_data = json.loads(Path(sys.argv[1]).read_text())
    for key, empty in (("overrides", {}), ("customItems", []), ("deleted", [])):
        app_data.setdefault(key, empty)

    if any(i.get("p") for i in app_data["customItems"]):
        print("Warning: some items are still pending; publishing anyway.", file=sys.stderr)

    src = INDEX_HTML.read_text()
    if not APP_DATA_RE.search(src):
        print("Could not find the app-data script tag in index.html", file=sys.stderr)
        sys.exit(1)

    # A literal </script> inside the JSON would close the tag early; the data
    # is titles and slugs, but escape defensively rather than trust that.
    payload = json.dumps(app_data).replace("\\", "\\\\").replace("</", "<\\/")
    updated = APP_DATA_RE.sub(lambda m: m.group(1) + payload + m.group(3), src, count=1)
    INDEX_HTML.write_text(updated)
    print(
        f"wrote app-data: {len(app_data['customItems'])} custom item(s), "
        f"{len(app_data['overrides'])} override(s), {len(app_data['deleted'])} deleted"
    )


if __name__ == "__main__":
    main()
