#!/usr/bin/env python3
"""Usage: python research.py example.com [--json] [--no-llm] [--max-pages N] [-o out.md]"""
import argparse
import json
import os
import sys

from companyresearch import heuristics, llm, report
from companyresearch.crawler import Crawler


def research(domain: str, use_llm: bool = True, max_pages: int = 25) -> dict:
    pages = Crawler(domain, max_pages=max_pages).crawl()
    data = heuristics.run(pages)
    if use_llm and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            ai = llm.run(pages)
            ai["contacts"] = data["contacts"]
            ai["pages_analyzed"] = data["pages_analyzed"]
            ai["heuristic_people"] = data["people"]
            return ai
        except Exception as e:  # fall back to rules
            print(f"[warn] LLM extraction failed ({e}); using rule-based result", file=sys.stderr)
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domain")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--max-pages", type=int, default=25)
    ap.add_argument("-o", "--output")
    a = ap.parse_args()
    data = research(a.domain, not a.no_llm, a.max_pages)
    out = json.dumps(data, indent=2) if a.json else report.render(data, a.domain)
    if a.output:
        open(a.output, "w").write(out)
    print(out)


if __name__ == "__main__":
    main()
