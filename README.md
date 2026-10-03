# Company Research Tool

Give it a domain; it crawls the company's website and reports: what they do and the kinds of
projects, employee count, current projects (and project counts), scope of work, and every person
named on the site (owner, executives, VPs, directors, managers, staff), plus contact details.

```bash
pip install -r requirements.txt
python research.py acmebuilders.com                 # markdown report
python research.py acmebuilders.com --json -o out.json
export ANTHROPIC_API_KEY=...                        # optional: much better extraction (uses Claude)
python research.py acmebuilders.com --no-llm        # rules only, fully offline from any API
```

How it works: `crawler.py` fetches the homepage + sitemap and ranks links (team, leadership, about,
projects, services, contact) then follows project/bio sub-pages; `heuristics.py` extracts with regex/JSON-LD;
`llm.py` (when an API key is set) has Claude read the pages and return structured JSON.

Limits: it only sees what the website says. Employee count is often absent from a site
(the report says so and gives the number of people listed as a lower bound); JS-rendered pages
and sites that block bots may return little. Check the site's terms of use / robots.txt before
bulk use. Local test fixture: `python tests/serve.py` then `python research.py http://127.0.0.1:8765 --no-llm`.
