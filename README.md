# dork — Google dork job scraper

This repository contains a small Python tool that runs a Google dork to discover public "careers" and "jobs" pages and writes the findings to `CAREERS.md`.

What it does

- Runs a dorked search (defaults to a query that finds `inurl:careers` and `inurl:jobs` pages).
- Prefers SerpAPI (when `SERPAPI_KEY` is provided) and falls back to a Google scraping heuristic (fragile).
- Deduplicates results, tags pages by detected path (`careers`, `jobs`, `search`, ...), and writes human-friendly Markdown to `CAREERS.md`.

Quickstart

1. Create and activate a virtualenv:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

2. (Recommended) Set your SerpAPI key in `.env` or as a repository secret named `SERPAPI_KEY`.

3. Run the scraper (examples):

```bash
# write results to CAREERS.md using SerpAPI
python job_scraper.py --engine serpapi --api-key YOUR_KEY --output CAREERS.md

# or use the scraping fallback (experimental)
python job_scraper.py --engine google --output CAREERS.md
```

Automation

- A GitHub Actions workflow runs daily and will update `CAREERS.md` automatically if a `SERPAPI_KEY` secret is configured. See `.github/workflows/update-readme.yml`.

Notes

- Prefer using SerpAPI or Google Custom Search for production use.
- The scraping fallback may break or get your runner IP rate-limited.

License

This project is licensed under the MIT License — see the [LICENSE](./LICENSE) file for details.