# This blog has moved to [joesec.me](https://joesec.me)

Everything published here now lives at **<https://joesec.me>**.

Old links still work. Each `/posts/…` URL serves a stub that forwards to its
new home, so bookmarks and inbound links land on the right article:

    /posts/2021-01-28-cors-blimey/  →  https://joesec.me/articles/cors-blimey/

The feed moved too: subscribe to <https://joesec.me/rss.xml>.

## What's in this repo

The Hugo source for the old site, kept as history. It is no longer published.
`.github/workflows/redirects.yml` builds the forwarding stubs instead, from
`build-redirects.py`.

GitHub Pages cannot issue a real `301`, so each stub pairs an instant
`<meta http-equiv="refresh">` with a `<link rel="canonical">`. Search engines
treat that as a soft redirect and pass ranking signals to the new URL.
