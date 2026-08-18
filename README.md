# Aviat

Daily aggregator of Aviat aircraft classified listings (Husky, Pitts, Eagle, etc.)
from [Barnstormers.com](https://www.barnstormers.com), published as a static page
(`docs/index.html`) meant to be embedded via `<iframe>` on taildraggers.com.

Controller.com was evaluated (in the companion [Aeronca](https://github.com/taildraggers/aeronca)
repo) and dropped: its search results are only reachable through an internal
client-side widget (not a plain URL), which a headless browser can't drive
reliably for an unattended daily job.

Barnstormers' "Aviat Aircraft" category page turned out to be loosely curated:
about 40% of the raw results were competing backcountry/aerobatic aircraft
(CubCrafters, a Cessna 175, American Champion Decathlons) with no distinguishing
HTML markup from the genuine listings. Results are filtered by title against
an allowlist of Aviat product names (`aviat`, `husky`, `pitts`, `christen eagle`)
before publishing — see `TARGET_MODEL_PHRASES` in `scraper/barnstormers.py`.

## How it works

- `scraper/barnstormers.py` searches Barnstormers.com's Aviat Aircraft category for
  listings, follows pagination, then keeps only the ones whose URL slug matches
  the Aviat product-name allowlist (Barnstormers builds each listing's URL
  slug directly from the ad's own title, so this runs before any detail page
  is fetched). For the matches, it visits each listing's detail page to pull
  out the price, location, and posted date (falling back to regex heuristics
  over the visible text since the site doesn't expose structured data). The
  title is derived from the listing URL's own SEO slug, since every detail page
  shares one generic `<title>`/`<h1>`; the final parsed title is checked
  against the allowlist again as a safety net.
- On top of that brand allowlist, only whole-aircraft-for-sale listings are kept.
  Each ad's title must state a model year and match a recognized Husky/Pitts/
  Christen Eagle model (see `_extract_model` in `scraper/barnstormers.py`); titles
  that read as parts, accessories, services, or raffles are dropped. Every
  surviving listing's title is rewritten to a canonical **`YEAR MAKE MODEL`**
  form - `Aviat` for Huskys, `Pitts` for the Pitts Special, `Christen` for the
  Christen Eagle, since that's how each is actually branded (e.g. `1988 Aviat
  Husky A-1`, `1995 Pitts S-2B`) - so the page reads consistently. A real side
  effect: ads that never state a model year in the title can't be reformatted
  and are dropped too, even if they're genuine aircraft.
- `main.py` runs the scraper, de-duplicates results, and renders them into
  `docs/index.html` titled **"Other Aviat Ads on the Web"**, with
  one row per listing: Title (linked to the original ad), Price, Location,
  Date Posted, and Site Posted On. Links use `rel="noopener noreferrer"` and
  the page sets a `no-referrer` meta policy, so Barnstormers never sees that
  the click came from taildraggers.com.
- `.github/workflows/daily-scrape.yml` runs the whole thing once a day (13:00 UTC),
  commits the regenerated `docs/index.html` if it changed, and can also be triggered
  manually from the Actions tab (`workflow_dispatch`).

## One-time setup: enable GitHub Pages

This repo publishes `docs/index.html` as a plain static file — GitHub Pages just needs
to be pointed at it once:

1. Go to **Settings → Pages** in this repository.
2. Under **Build and deployment → Source**, choose **Deploy from a branch**.
3. Branch: `main`, folder: `/docs`. Save.
4. GitHub will publish the page at `https://taildraggers.github.io/aviat/`
   (may take a minute or two the first time).

Also check **Settings → Actions → General**:
- **Actions permissions**: "Allow all actions and reusable workflows".
- **Workflow permissions**: "Read and write permissions" (needed so the daily
  job can commit the regenerated page back to the repo).

## Embedding on taildraggers.com

```html
<iframe
  src="https://taildraggers.github.io/aviat/"
  title="Other Aviat Ads on the Web"
  style="width: 100%; height: 800px; border: 0;"
  loading="lazy">
</iframe>
```

## Running locally

```bash
pip install -r requirements.txt
playwright install --with-deps chromium
python main.py
```

This writes/overwrites `docs/index.html`.

## Notes

- If Barnstormers changes its markup or is briefly unreachable, the run logs will
  show a `[warn]`/`[error]` line pointing at what broke rather than failing silently.
- The scraper identifies itself with a browser-like `User-Agent` and adds a short
  delay between requests to be polite to the site.
- Only one Barnstormers category is currently configured
  (`category-24045-Aviat-Aircraft.html`). If Aviat listings turn out to be split
  across additional categories (the way Aeronca and American Champion are), add
  more URLs to `CATEGORY_URLS` in `scraper/barnstormers.py`.
