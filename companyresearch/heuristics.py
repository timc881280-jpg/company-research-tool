"""Rule-based extraction. Works offline from the crawled pages; used on its own
(no API key) or as a fallback/cross-check for the LLM extractor."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from .crawler import Page, score_url

TITLE_RE = re.compile(
    r"\b(chief [a-z]+ officer|c[eofitmp]o|founder|co-?founder|owner|president|"
    r"vice president|vp\b|svp|evp|managing (director|partner|member)|principal|"
    r"partner|director|general manager|manager|chairman|chairwoman|chair\b|"
    r"superintendent|head of [a-z ]+|estimator|architect|engineer)\b", re.I)
SENIOR_RE = re.compile(
    r"\b(chief|ceo|cfo|coo|cto|cio|founder|owner|president|vp\b|svp|evp|vice president|"
    r"managing|principal|partner|chair|director|general manager)\b", re.I)
NAME_RE = re.compile(
    r"^(?:(?:Dr|Mr|Mrs|Ms)\.? )?[A-Z][a-zA-Z'’.-]+(?: [A-Z][a-zA-Z'’.-]*\.?){1,3}"
    r"(?:,? (?:Jr|Sr|II|III|PE|P\.E\.|AIA|LEED AP|PMP|CPA|MBA|PhD)\.?)*$")
NOT_NAME = re.compile(r"\b(team|about|contact|read|more|learn|our|view|meet|leadership|"
                      r"services|projects?|company|careers?|home|us|the|and|of|for)\b", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?:\+?1[ .-])?\(?\b\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b")

EMP_RES = [
    re.compile(r"(?P<n>\d{1,3}(?:,\d{3})+|\d+)\+?\s*(?:full[- ]time\s+)?"
               r"(?:employees|team members|professionals|staff|associates|people|craftsmen|experts)\b", re.I),
    re.compile(r"(?:team|staff|workforce|company) of (?:over |more than |approximately |about )?"
               r"(?P<n>\d{1,3}(?:,\d{3})+|\d+)\+?", re.I),
    re.compile(r"(?:over|more than|approximately|about|nearly)\s+(?P<n>\d{1,3}(?:,\d{3})+|\d+)\s+"
               r"(?:employees|team members|professionals|staff|people)", re.I),
]
PROJECT_COUNT_RE = re.compile(
    r"(?P<n>\d{1,3}(?:,\d{3})+|\d+)\+?\s*(?:completed\s+|successful\s+|active\s+|ongoing\s+)?"
    r"(?:projects|developments|buildings|properties|installations|clients served)\b", re.I)
FOUNDED_RE = re.compile(r"\b(?:founded|established|since|est\.?)\s*(?:in\s*)?((?:18|19|20)\d{2})\b", re.I)


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def extract_contacts(pages: list[Page]) -> dict:
    emails, phones = set(), set()
    for p in pages:
        emails |= {e.lower() for e in EMAIL_RE.findall(p.text) if not e.lower().endswith(("png", "jpg"))}
        phones |= set(PHONE_RE.findall(p.text))
    return {"emails": sorted(emails)[:15], "phones": sorted(phones)[:10]}


def extract_employee_count(pages: list[Page], people_found: int) -> dict:
    for p in pages:
        for item in p.jsonld:
            n = item.get("numberOfEmployees")
            if isinstance(n, dict):
                n = n.get("value") or n.get("minValue")
            if n:
                return {"value": str(n), "source": p.url, "basis": "structured data (JSON-LD)"}
    for p in pages:
        for rx in EMP_RES:
            m = rx.search(p.text)
            if m and 1 <= _num(m["n"]) <= 500000:
                return {"value": m["n"] + "+", "source": p.url,
                        "basis": f'stated on site: "{m.group(0).strip()}"'}
    if people_found:
        return {"value": f"at least {people_found}", "source": "team pages",
                "basis": "count of people listed on website (lower bound)"}
    return {"value": None, "source": None,
            "basis": "not stated on website; check LinkedIn / ZoomInfo / state filings"}


def extract_org(pages: list[Page]) -> dict:
    out = {"name": None, "description": None, "founded": None, "address": None}
    home = pages[0]
    for p in pages:
        for item in p.jsonld:
            t = item.get("@type")
            t = t if isinstance(t, list) else [t]
            if any(x in ("Organization", "LocalBusiness", "Corporation", "GeneralContractor",
                         "ProfessionalService") for x in t if x):
                out["name"] = out["name"] or item.get("name")
                out["description"] = out["description"] or item.get("description")
                out["founded"] = out["founded"] or item.get("foundingDate")
                a = item.get("address")
                if isinstance(a, dict) and not out["address"]:
                    out["address"] = ", ".join(str(a.get(k)) for k in
                        ("streetAddress", "addressLocality", "addressRegion", "postalCode") if a.get(k))
    if not out["name"]:
        out["name"] = re.split(r"\s[|\-–—]\s", home.title)[0].strip() or None
    if not out["description"]:
        m = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', home.html, re.I) \
            or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description', home.html, re.I)
        out["description"] = m.group(1).strip() if m else None
    if not out["founded"]:
        for p in pages:
            m = FOUNDED_RE.search(p.text)
            if m:
                out["founded"] = m.group(1)
                break
    return out


def _clean_name(s: str) -> str | None:
    s = re.sub(r"\s+", " ", s).strip(" ,|-–—:•")
    if 4 <= len(s) <= 40 and NAME_RE.match(s) and not NOT_NAME.search(s) and not TITLE_RE.search(s):
        return s
    return None


def extract_people(pages: list[Page]) -> list[dict]:
    people: dict[str, dict] = {}

    def add(name, title, url, email=None):
        key = name.lower()
        if key in people:
            if len(title) > len(people[key]["title"] or ""):
                people[key]["title"] = title
            return
        people[key] = {"name": name, "title": title, "source": url,
                       "senior": bool(SENIOR_RE.search(title or ""))}

    for p in pages:
        for item in p.jsonld:
            if item.get("@type") == "Person" and item.get("name"):
                add(item["name"], item.get("jobTitle", ""), p.url)
        lines = [l.strip() for l in p.text.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if len(line) > 90 or not TITLE_RE.search(line):
                continue
            # "Jane Doe, Chief Executive Officer" / "Jane Doe – VP of Ops"
            parts = re.split(r"\s*[,|–—:]\s*|\s+-\s+", line, maxsplit=1)
            if len(parts) == 2:
                for n, t in ((parts[0], parts[1]), (parts[1], parts[0])):
                    name = _clean_name(n)
                    if name and TITLE_RE.search(t):
                        add(name, t.strip(), p.url)
                        break
                else:
                    continue
                continue
            # title on its own line; name on the line before or after
            for j in (i - 1, i + 1):
                if 0 <= j < len(lines):
                    name = _clean_name(lines[j])
                    if name:
                        add(name, line, p.url)
                        break
    result = list(people.values())
    result.sort(key=lambda x: (not x["senior"], x["name"]))
    return result


def extract_projects(pages: list[Page], base_host: str) -> dict:
    stated = None
    for p in pages:
        m = PROJECT_COUNT_RE.search(p.text)
        if m and (stated is None or _num(m["n"]) > stated["n"]):
            stated = {"n": _num(m["n"]), "text": m.group(0), "source": p.url}

    hub_pages = [p for p in pages
                 if re.search(r"project|portfolio|case-stud|our-work|/work", urlparse(p.url).path, re.I)]
    items: dict[str, dict] = {}
    for hub in hub_pages:
        hub_path = urlparse(hub.url).path.rstrip("/")
        for url, anchor in hub.links:
            u = urlparse(url)
            if u.netloc.removeprefix("www.") != base_host.removeprefix("www."):
                continue
            # child pages of the hub: /projects/foo
            if hub_path and u.path.rstrip("/").startswith(hub_path + "/") and len(anchor) > 3 \
                    and anchor.lower() not in ("read more", "learn more", "view project", "view all"):
                items.setdefault(url, {"name": anchor, "url": url})
    # enrich with first descriptive line from the project's own page
    by_url = {p.url: p for p in pages}
    for url, it in items.items():
        pg = by_url.get(url)
        if pg:
            body = [l for l in pg.text.split("\n") if len(l) > 60]
            it["summary"] = body[0][:300] if body else ""
            txt = pg.text.lower()
            it["status"] = ("current" if re.search(r"under construction|in progress|ongoing|currently|upcoming|coming soon", txt)
                            else "completed" if re.search(r"completed|delivered|opened|finished", txt) else "unknown")
    if not items:  # no sub-pages: use headings on the hub page itself
        for hub in hub_pages:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(hub.html, "lxml")
            for h in soup.find_all(["h2", "h3", "h4"]):
                t = h.get_text(" ", strip=True)
                if 4 < len(t) < 90 and not re.search(r"project|portfolio|contact|about|services", t, re.I):
                    items.setdefault(t, {"name": t, "url": hub.url})
    listed = list(items.values())
    return {"stated_count": stated, "listed_count": len(listed), "projects": listed[:60]}


def extract_scope(pages: list[Page]) -> list[str]:
    """Service / sector names from nav-ish short lines on services pages."""
    out: list[str] = []
    for p in pages:
        if not re.search(r"service|capabilit|expertise|what-we-do|sector|market", urlparse(p.url).path, re.I):
            continue
        for l in p.text.split("\n"):
            l = l.strip()
            if 3 < len(l) < 50 and l[0].isupper() and not re.fullmatch(r"(?i)services?|our services|capabilities|what we do", l) and not l.endswith((".", "!")) and l not in out \
                    and not re.search(r"contact|home|about|careers|©|privacy|menu|search|learn more", l, re.I):
                out.append(l)
    return out[:40]


def run(pages: list[Page]) -> dict:
    host = urlparse(pages[0].url).netloc
    people = extract_people(pages)
    return {
        "company": extract_org(pages),
        "employee_count": extract_employee_count(pages, len(people)),
        "people": people,
        "projects": extract_projects(pages, host),
        "scope_of_work": extract_scope(pages),
        "contacts": extract_contacts(pages),
        "pages_analyzed": [p.url for p in pages],
    }
