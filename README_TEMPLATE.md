# Job scraper README template

This repository contains a single-file job scraper that runs a Google dork and writes results to a Markdown file.

Usage

```
python job_scraper.py --engine serpapi --api-key YOUR_KEY --max 50 --output README.md
```

Output format

- Header with query, engine, timestamp, and counts
- Grouped results by domain
- Each result: title (linked), optional tag (e.g. `careers`, `jobs`), and short snippet

Notes

- Prefer using SerpAPI (pass `--engine serpapi` and `--api-key`).
- The `google` engine is a fragile scraping fallback and may break or get blocked.

