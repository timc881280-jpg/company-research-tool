from __future__ import annotations


def render(d: dict, domain: str) -> str:
    c = d["company"]
    o = [f"# Company research: {domain}", ""]
    o += [f"**Name:** {c.get('name') or 'n/a'}"]
    if c.get("industry"):
        o += [f"**Industry:** {c['industry']}"]
    if c.get("project_types"):
        o += [f"**Kinds of projects:** {', '.join(c['project_types'])}"]
    o += [f"**What they do:** {c.get('description') or 'n/a'}",
          f"**Founded:** {c.get('founded') or 'n/a'}   **Address:** {c.get('address') or 'n/a'}", ""]
    e = d["employee_count"]
    o += ["## Employee count", f"{e.get('value') or 'unknown'}  — {e.get('basis')}", ""]

    o += ["## Scope of work"] + [f"- {s}" for s in d.get("scope_of_work", [])] + [""]

    p = d["projects"]
    sc = p.get("stated_count")
    sc = sc.get("text") if isinstance(sc, dict) else sc
    o += ["## Projects",
          f"Stated on site: {sc or 'n/a'} · Listed on site: {p.get('listed_count', 0)}", ""]
    for pr in p.get("current") or p.get("projects") or []:
        bits = [x for x in (pr.get("type"), pr.get("location"), pr.get("status")) if x]
        o.append(f"- **{pr['name']}**" + (f" ({', '.join(bits)})" if bits else "")
                 + (f" — {pr['summary']}" if pr.get("summary") else ""))
    o.append("")

    o += ["## People named on the website"]
    for group, label in (("senior", "Owners / executives / VPs / directors"), ("other", "Others")):
        rows = [x for x in d["people"] if (x.get("senior") if "senior" in x
                else x.get("role_category") in ("owner", "executive", "vp", "director")) == (group == "senior")]
        if rows:
            o += [f"**{label}**"]
            o += [f"- {x['name']} — {x.get('title') or '?'}" for x in rows]
    o.append("")
    ct = d["contacts"]
    o += ["## Contacts", f"Emails: {', '.join(ct['emails']) or 'n/a'}",
          f"Phones: {', '.join(ct['phones']) or 'n/a'}", ""]
    if d.get("notes"):
        o += ["## Notes", d["notes"], ""]
    o += [f"_Pages analyzed: {len(d['pages_analyzed'])}_"]
    return "\n".join(o)
