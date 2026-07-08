#!/usr/bin/env python3
"""Generate the redirect shim that replaces this Hugo site.

The blog moved to https://joesec.me. GitHub Pages cannot issue a 301 — there is
no server config, and a user-page CNAME cannot point at a domain served
elsewhere. The best available is a stub per URL: an instant meta refresh plus a
rel=canonical. Search engines treat that pair as a soft redirect and pass
ranking signals through the canonical.

Post URLs lost their date prefix in the move:

    /posts/2021-01-28-cors-blimey/  ->  https://joesec.me/articles/cors-blimey/

Anything not covered by a stub lands on 404.html, which re-derives that same
mapping in JS and otherwise sends the visitor home. That path returns a 404
status, so it rescues humans but not link equity — hence the explicit stubs.
"""

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
CONTENT = ROOT / "content" / "posts"
OUT = ROOT / "redirect-site"
NEW = "https://joesec.me"

DATED = re.compile(r"^\d{4}-\d{2}-\d{2}-")


def stub(target: str, title: str) -> str:
    """A page whose only job is to leave. Canonical carries the SEO signal."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Moved to joesec.me</title>
<link rel="canonical" href="{target}">
<meta http-equiv="refresh" content="0; url={target}">
<meta name="robots" content="noindex, follow">
<style>
  body {{ background:#0c1116; color:#e7edf2; font:17px/1.6 system-ui,sans-serif;
         display:grid; place-items:center; min-height:100vh; margin:0; }}
  a {{ color:#8aa3ff; }}
</style>
</head>
<body>
<p>{title} has moved to <a href="{target}">{target}</a>.</p>
<script>location.replace({target!r});</script>
</body>
</html>
"""


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    pages = {
        "": (f"{NEW}/", "This site"),
        # no About page on the new site — send them to the front door
        "about": (f"{NEW}/", "The about page"),
        "posts": (f"{NEW}/articles/", "The article index"),
    }

    for md in sorted(CONTENT.glob("*.md")):
        old = md.stem
        new = DATED.sub("", old)
        if new == old:
            raise SystemExit(f"post filename has no date prefix, refusing to guess: {md.name}")
        pages[f"posts/{old}"] = (f"{NEW}/articles/{new}/", "This article")

    for path, (target, title) in pages.items():
        d = OUT / path if path else OUT
        d.mkdir(parents=True, exist_ok=True)
        (d / "index.html").write_text(stub(target, title))

    # Feed readers ignore HTML, so a meta refresh cannot reach them. Serve a
    # frozen feed whose single item tells a human subscriber where to go.
    (OUT / "index.xml").write_text(f"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
<channel>
  <title>Joe Bollen — Security (moved)</title>
  <link>{NEW}/</link>
  <description>This feed has moved to {NEW}/rss.xml</description>
  <atom:link href="{NEW}/rss.xml" rel="self" type="application/rss+xml"/>
  <item>
    <title>This feed has moved to joesec.me</title>
    <link>{NEW}/rss.xml</link>
    <guid isPermaLink="false">joesec-me-feed-moved-2026</guid>
    <description>Subscribe to {NEW}/rss.xml to keep receiving new articles.</description>
  </item>
</channel>
</rss>
""")

    # Keep the old URLs in a sitemap so crawlers revisit them and find the
    # canonicals, rather than waiting to rediscover them organically.
    locs = "".join(
        f"<url><loc>https://joe-b-security.github.io/{p}{'/' if p else ''}</loc></url>"
        for p in pages
    )
    (OUT / "sitemap.xml").write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>\n'
    )

    (OUT / "robots.txt").write_text(
        "User-agent: *\nAllow: /\nSitemap: https://joe-b-security.github.io/sitemap.xml\n"
    )

    # GitHub Pages serves this for any path without a stub: tag, category,
    # series, author and /page/N listings, plus anything we've forgotten.
    (OUT / "404.html").write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Moved to joesec.me</title>
<meta name="robots" content="noindex, follow">
<style>
  body {{ background:#0c1116; color:#e7edf2; font:17px/1.6 system-ui,sans-serif;
         display:grid; place-items:center; min-height:100vh; margin:0; }}
  a {{ color:#8aa3ff; }}
</style>
</head>
<body>
<p>This site has moved to <a href="{NEW}/">{NEW}</a>.</p>
<script>
  var m = location.pathname.match(/^\\/posts\\/\\d{{4}}-\\d{{2}}-\\d{{2}}-(.+?)\\/?$/);
  location.replace(m ? {NEW!r} + '/articles/' + m[1] + '/' : {NEW!r} + '/');
</script>
</body>
</html>
""")

    print(f"wrote {len(pages)} stubs + 404.html, index.xml, sitemap.xml, robots.txt -> {OUT}")


if __name__ == "__main__":
    main()
