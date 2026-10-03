"""Fetch a company website: homepage, sitemap, and the pages likely to hold
about / team / leadership / project / careers information."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (compatible; CompanyResearchBot/1.0)"

# path keywords -> relevance weight (higher = fetched first)
PAGE_HINTS = {
    "team": 10, "leadership": 10, "management": 10, "people": 9, "staff": 9,
    "executive": 9, "our-team": 10, "meet": 8, "board": 7, "bio": 6,
    "about": 9, "company": 7, "who-we-are": 8, "story": 5,
    "project": 9, "portfolio": 9, "work": 6, "case-stud": 8, "case": 4,
    "services": 6, "capabilit": 6, "expertise": 5, "sector": 4, "markets": 4,
    "career": 6, "jobs": 5, "join": 4, "contact": 6, "news": 3, "press": 3,
}
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|mp4|mp3|css|js|ico|xml|docx?|xlsx?)(\?|$)", re.I)


@dataclass
class Page:
    url: str
    title: str
    text: str            # visible text, one block per line
    links: list[tuple[str, str]]   # (absolute url, anchor text)
    jsonld: list[dict] = field(default_factory=list)
    html: str = ""


def normalize_domain(domain: str) -> str:
    domain = domain.strip()
    if not re.match(r"^https?://", domain):
        domain = "https://" + domain
    p = urlparse(domain)
    return f"{p.scheme}://{p.netloc}"


def parse_page(url: str, html: str) -> Page:
    import json
    soup = BeautifulSoup(html, "lxml")
    jsonld: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict):
                jsonld.extend(it["@graph"] if isinstance(it.get("@graph"), list) else [it])
    links = []
    for a in soup.find_all("a", href=True):
        href = urldefrag(urljoin(url, a["href"]))[0]
        if href.startswith("http"):
            links.append((href, a.get_text(" ", strip=True)))
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    text = soup.get_text("\n", strip=True)
    title = soup.title.get_text(strip=True) if soup.title else ""
    return Page(url, title, text, links, jsonld, html)


def _same_site(host_a: str, host_b: str) -> bool:
    strip = lambda h: h.lower().removeprefix("www.")
    return strip(host_a) == strip(host_b)


def score_url(url: str, anchor: str = "") -> int:
    s = (urlparse(url).path + " " + anchor).lower()
    return max((w for k, w in PAGE_HINTS.items() if k in s), default=0)


class Crawler:
    def __init__(self, domain: str, max_pages: int = 25, timeout: float = 15.0):
        self.base = normalize_domain(domain)
        self.host = urlparse(self.base).netloc
        self.max_pages = max_pages
        self.client = httpx.Client(headers={"User-Agent": UA}, timeout=timeout,
                                   follow_redirects=True)
        self.pages: dict[str, Page] = {}
        self.sitemap_urls: list[str] = []

    def fetch(self, url: str) -> Page | None:
        if url in self.pages or SKIP_EXT.search(url):
            return self.pages.get(url)
        try:
            r = self.client.get(url)
        except httpx.HTTPError:
            return None
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
            return None
        # follow a redirect to another host (e.g. example.com -> www.example.com)
        if not _same_site(urlparse(str(r.url)).netloc, self.host):
            return None
        self.host = urlparse(str(r.url)).netloc
        page = parse_page(str(r.url), r.text)
        self.pages[url] = page
        return page

    def load_sitemap(self) -> None:
        todo = [urljoin(self.base, "/sitemap.xml")]
        seen = set()
        while todo and len(seen) < 6:
            sm = todo.pop(0)
            if sm in seen:
                continue
            seen.add(sm)
            try:
                r = self.client.get(sm)
            except httpx.HTTPError:
                continue
            if r.status_code != 200:
                continue
            for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text):
                if loc.endswith(".xml"):
                    todo.append(loc)
                else:
                    self.sitemap_urls.append(loc)

    def crawl(self) -> list[Page]:
        home = self.fetch(self.base + "/")
        if home is None:
            home = self.fetch(f"https://www.{urlparse(self.base).netloc}/")
        if home is None:
            raise RuntimeError(f"Could not fetch {self.base}")
        self.load_sitemap()
        candidates: dict[str, int] = {}
        for url, anchor in home.links:
            if _same_site(urlparse(url).netloc, self.host):
                candidates[url] = max(candidates.get(url, 0), score_url(url, anchor))
        for url in self.sitemap_urls:
            if _same_site(urlparse(url).netloc, self.host):
                candidates[url] = max(candidates.get(url, 0), score_url(url))
        queue = sorted((u for u, s in candidates.items() if s > 0),
                       key=lambda u: (-candidates[u], len(u)))
        for url in queue:
            if len(self.pages) >= self.max_pages:
                break
            page = self.fetch(url)
            # one more hop: team/project index pages link to individual bios/projects
            if page and candidates[url] >= 8:
                for l, a in page.links:
                    if (_same_site(urlparse(l).netloc, self.host) and l not in candidates
                            and score_url(l, a) >= 6):
                        candidates[l] = 5
                        queue.append(l)
        return list(self.pages.values())
