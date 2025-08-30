#!/usr/bin/env python3
"""
job_scraper.py - Google dork job scraper (SerpAPI preferred, Google scraping fallback).

Usage examples:
  python job_scraper.py --engine serpapi --api-key YOUR_KEY --max 50 --output README.md
  python job_scraper.py --engine google --max 20 --output README.md
"""

from __future__ import annotations
import argparse
import os
import sys
import time
import random
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple
from urllib.parse import urlparse, urlunparse

# Optional imports (fail with helpful message)
try:
    import requests
    from bs4 import BeautifulSoup
except Exception as e:
    print("Missing dependency. Install requirements with: pip install -r requirements.txt", file=sys.stderr)
    raise

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv optional
    pass

USER_AGENTS = [
    # minimal UA list; feel free to expand
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/115.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
]

DEFAULT_DORK = '(inurl:careers OR inurl:jobs) (inurl:open OR inurl:positions OR inurl:listings OR inurl:vacancies OR inurl:search)'
JOB_PATH_KEYWORDS = ["careers", "jobs", "vacancies", "positions", "listings", "open", "search"]

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Google dork job scraper (SerpAPI preferred, Google scrape fallback)")
    p.add_argument("--query", default=os.getenv("QUERY", DEFAULT_DORK), help="Search query / dork")
    p.add_argument("--engine", choices=("serpapi", "google"), default=os.getenv("ENGINE", "serpapi"), help="Search engine/mode")
    p.add_argument("--api-key", default=os.getenv("SERPAPI_KEY") or os.getenv("API_KEY"), help="SerpAPI key (preferred)")
    p.add_argument("--max", type=int, default=50, help="Maximum results to fetch")
    p.add_argument("--delay", type=float, default=1.0, help="Base delay between requests (seconds)")
    p.add_argument("--output", default=os.getenv("OUTPUT", "README.md"), help="Output markdown file")
    p.add_argument("--proxy", default=os.getenv("HTTP_PROXY") or os.getenv("PROXY"), help="Optional proxy URL (http://user:pass@host:port)")
    p.add_argument("--no-verify-ssl", action="store_true", help="Disable SSL verify for requests (not recommended)")
    return p.parse_args()

def normalize_url(url: str) -> str:
    try:
        p = urlparse(url)
        # Keep scheme, netloc, and path. Strip query and fragment for dedupe.
        return urlunparse((p.scheme or "https", p.netloc.lower(), p.path.rstrip("/"), "", "", ""))
    except Exception:
        return url

def tag_path(url: str) -> Optional[str]:
    try:
        p = urlparse(url)
        path = p.path.lower()
        for kw in JOB_PATH_KEYWORDS:
            if f"/{kw}" in path or path.endswith(kw):
                return kw
        # also consider query
        q = p.query.lower()
        for kw in JOB_PATH_KEYWORDS:
            if kw in q:
                return kw
    except Exception:
        pass
    return None

def dedupe_results(items: List[Dict]) -> List[Dict]:
    seen = set()
    out = []
    for it in items:
        norm = normalize_url(it.get("url") or it.get("link") or "")
        if not norm:
            continue
        key = norm
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out

def format_entry(item: Dict) -> Dict:
    title = item.get("title") or item.get("title_noformatting") or ""
    url = item.get("link") or item.get("url") or ""
    snippet = item.get("snippet") or item.get("snippet") or item.get("description") or ""
    tag = tag_path(url)
    return {
        "title": title.strip(),
        "url": url,
        "snippet": snippet.strip(),
        "tag": tag or "",
        "domain": urlparse(url).netloc.lower()
    }

# ---------- SerpAPI ----------
def search_serpapi(query: str, api_key: str, num: int = 50, proxies: Optional[Dict] = None, verify_ssl: bool = True, delay: float = 1.0) -> List[Dict]:
    """
    Uses SerpAPI (https://serpapi.com/) to fetch results. Returns list of raw result dicts.
    """
    if not api_key:
        raise ValueError("SerpAPI key required for search_serpapi")
    endpoint = "https://serpapi.com/search.json"
    results = []
    session = requests.Session()
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    page = 0
    per_page = 10  # serpapi supports 'num' but a safe per-page increment
    while len(results) < num:
        params = {
            "q": query,
            "engine": "google",
            "api_key": api_key,
            "start": page * per_page,
            "num": per_page,
            "hl": "en",
        }
        try:
            r = session.get(endpoint, params=params, headers=headers, proxies=proxies or {}, timeout=30, verify=verify_ssl)
            r.raise_for_status()
            data = r.json()
            organic = data.get("organic_results") or data.get("organic") or []
            if not organic:
                break
            for o in organic:
                results.append(o)
                if len(results) >= num:
                    break
            page += 1
            time.sleep(delay + random.random() * 0.5)
        except Exception as e:
            # simple backoff
            for attempt in range(1, 4):
                backoff = (2 ** attempt) + random.random()
                time.sleep(backoff)
                try:
                    r = session.get(endpoint, params=params, headers=headers, proxies=proxies or {}, timeout=30, verify=verify_ssl)
                    r.raise_for_status()
                    data = r.json()
                    organic = data.get("organic_results") or []
                    if organic:
                        for o in organic:
                            results.append(o)
                            if len(results) >= num:
                                break
                        break
                except Exception:
                    continue
            else:
                break
    return results[:num]

# ---------- Google scraping fallback ----------
def parse_google_result(div) -> Optional[Dict]:
    # Attempts to extract title, link, snippet from a Google search result block
    a = div.find("a", href=True)
    if not a:
        return None
    href = a["href"]
    # skip navigational URLs that start with '/search' etc.
    if href.startswith("/"):
        # sometimes google wraps with /url?q=<target>&...
        if href.startswith("/url?q="):
            import urllib.parse as up
            q = href.split("/url?q=", 1)[1]
            target = q.split("&", 1)[0]
            href = up.unquote(target)
        else:
            return None
    title_tag = div.find("h3")
    title = title_tag.get_text(strip=True) if title_tag else a.get_text(strip=True)
    snippet = ""
    # snippet candidates
    s = div.find("div", {"class": "IsZvec"})
    if s:
        snippet = s.get_text(" ", strip=True)
    else:
        s2 = div.find("div", {"class": "BNeawe"})
        if s2:
            snippet = s2.get_text(" ", strip=True)
    return {"title": title, "link": href, "snippet": snippet}

def search_google_scrape(query: str, num: int = 50, delay: float = 1.0, proxies: Optional[Dict] = None, verify_ssl: bool = True) -> List[Dict]:
    """
    Fragile Google scraping fallback. Use only for quick experiments.
    Observes rate limiting and UA rotation.
    """
    results = []
    session = requests.Session()
    per_page = 10
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    for start in range(0, num, per_page):
        params = {"q": query, "start": start, "hl": "en", "num": per_page}
        try:
            r = session.get("https://www.google.com/search", params=params, headers=headers, proxies=proxies or {}, timeout=30, verify=verify_ssl)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")
            # Google result blocks vary. look for 'div.g' first
            items = soup.select("div.g")
            if not items:
                # fallback heuristics
                items = soup.select("div[data-hveid]")
            for div in items:
                parsed = parse_google_result(div)
                if parsed:
                    results.append(parsed)
                    if len(results) >= num:
                        break
            time.sleep(delay + random.random() * 1.5)
            # rotate UA
            headers["User-Agent"] = random.choice(USER_AGENTS)
            if len(results) >= num:
                break
        except Exception:
            # backoff
            time.sleep((2 ** (start // per_page)) + random.random())
            # try again once
            continue
    return results[:num]

# ---------- Output / Writing ----------
def generate_markdown(query: str, engine: str, items: List[Dict], meta: Dict, output_path: str) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat()
    total = len(items)
    groups: Dict[str, List[Dict]] = {}
    for it in items:
        domain = it.get("domain") or urlparse(it.get("url", "")).netloc or "unknown"
        groups.setdefault(domain, []).append(it)
    lines = []
    lines.append(f"# Job results for: `{query}`")
    lines.append("")
    lines.append(f"_Engine: {engine}  |  Generated: {now}  |  Results: {total}_")
    if meta:
        lines.append("")
        lines.append("**Search metadata**:")
        for k, v in meta.items():
            lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Results grouped by domain")
    lines.append("")
    for domain, entries in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        lines.append(f"### {domain} — {len(entries)} result(s)")
        lines.append("")
        for e in entries:
            title = e.get("title") or e.get("url")
            snippet = e.get("snippet") or ""
            tag = f" — `{e['tag']}`" if e.get("tag") else ""
            # short snippet
            if len(snippet) > 200:
                snippet = snippet[:197].rstrip() + "..."
            lines.append(f"- [{title}]({e.get('url')}){tag}  ")
            if snippet:
                lines.append(f"  - _{snippet}_")
        lines.append("")
    content = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"Wrote {total} results to {output_path}")

def main():
    args = parse_args()
    proxies = None
    if args.proxy:
        proxies = {"http": args.proxy, "https": args.proxy}
    verify_ssl = not args.no_verify_ssl
    print(f"Query: {args.query!r}")
    print(f"Engine: {args.engine}  Max: {args.max}  Delay: {args.delay}s")
    raw_results = []
    meta = {}
    if args.engine == "serpapi" and args.api_key:
        try:
            raw_results = search_serpapi(args.query, api_key=args.api_key, num=args.max, proxies=proxies, verify_ssl=verify_ssl, delay=args.delay)
            meta["source"] = "serpapi"
        except Exception as e:
            print("SerpAPI failed or missing key; falling back to google scrape:", e, file=sys.stderr)
            raw_results = search_google_scrape(args.query, num=args.max, delay=args.delay, proxies=proxies, verify_ssl=verify_ssl)
            meta["source"] = "google_scrape_fallback"
    else:
        raw_results = search_google_scrape(args.query, num=args.max, delay=args.delay, proxies=proxies, verify_ssl=verify_ssl)
        meta["source"] = "google_scrape"
    # normalize / format / dedupe
    formatted = [format_entry(r) for r in raw_results]
    deduped = dedupe_results(formatted)
    # optionally filter to those that match job-related path, but keep all and mark tags
    # write output
    meta["fetched"] = len(raw_results)
    meta["deduped"] = len(deduped)
    generate_markdown(args.query, meta.get("source", args.engine), deduped, meta, args.output)

if __name__ == "__main__":
    main()
