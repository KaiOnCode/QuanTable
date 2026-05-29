"""Verify all DOIs in refs.bib against CrossRef and arXiv APIs."""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

PWD = Path(__file__).parent


def parse_bib(path: str) -> list[dict]:
    text = Path(path).read_text()
    entries = []
    for block in re.finditer(r"@\w+\{([\w:.\-]+),\s*(.*?)\n\}", text, re.DOTALL):
        key = block.group(1)
        body = block.group(2)
        fields = {}
        for m in re.finditer(r"(\w+)\s*=\s*\{(.*?)\}", body, re.DOTALL):
            fields[m.group(1).strip()] = m.group(2).strip()
        fields["_key"] = key
        entries.append(fields)
    return entries


def query_crossref(doi: str) -> dict | None:
    url = f"https://api.crossref.org/works/{doi}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "BibVerifier/1.0 (mailto:test@test.com)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data.get("message", {})
    except (urllib.error.HTTPError, urllib.error.URLError, Exception):
        return None


def query_arxiv(arxiv_id: str) -> dict | None:
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            xml = resp.read().decode()
            entry_m = re.search(r"<entry>(.*?)</entry>", xml, re.DOTALL)
            if not entry_m:
                return None
            entry_xml = entry_m.group(1)
            title_m = re.search(r"<title>(.*?)</title>", entry_xml, re.DOTALL)
            authors = re.findall(r"<name>(.*?)</name>", entry_xml)
            if title_m:
                title = re.sub(r"\s+", " ", title_m.group(1)).strip()
                return {"title": title, "authors": authors}
    except Exception:
        pass
    return None


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def compare_titles(bib_title: str, api_title: str) -> tuple[bool, str]:
    nb = normalize(bib_title)
    na = normalize(api_title)
    if nb == na:
        return True, "exact match"
    if nb in na or na in nb:
        return True, "substring match"
    words_b = set(nb.split())
    words_a = set(na.split())
    if len(words_b) == 0:
        return False, "empty bib title"
    overlap = len(words_b & words_a) / max(len(words_b), len(words_a))
    if overlap > 0.7:
        return True, f"word overlap {overlap:.0%}"
    return False, f"word overlap {overlap:.0%} (LOW)"


def main(name: str = "refs.bib"):
    entries = parse_bib(PWD / name)
    print(f"Found {len(entries)} BibTeX entries\n")
    print("=" * 90)

    ok_count = 0
    warn_count = 0
    fail_count = 0

    for e in entries:
        key = e["_key"]
        bib_title = e.get("title", "")
        doi = e.get("doi", "")
        url = e.get("url", "")
        print(f"\n[{key}]")
        print(f"  BIB title : {bib_title[:80]}...")

        arxiv_match = re.search(r"arXiv[.:](\d{4}\.\d{4,5})", doi or "")
        if not arxiv_match:
            arxiv_match = re.search(r"arXiv[.:](\d{4}\.\d{4,5})", e.get("journal", ""))

        verified_via = None
        api_title = None

        # Try arXiv first for arXiv papers
        if arxiv_match:
            arxiv_id = arxiv_match.group(1)
            print(f"  arXiv ID  : {arxiv_id}")
            result = query_arxiv(arxiv_id)
            if result and result["title"]:
                api_title = result["title"]
                verified_via = "arXiv"
                print(f"  API title : {api_title[:80]}...")
                print(f"  Authors   : {', '.join(result['authors'][:3])}...")

        # Try CrossRef for DOIs (non-arXiv or as fallback)
        if not api_title and doi and not doi.startswith("10.48550/arXiv"):
            print(f"  DOI       : {doi}")
            result = query_crossref(doi)
            if result:
                titles = result.get("title", [])
                api_title = titles[0] if titles else None
                verified_via = "CrossRef"
                if api_title:
                    print(f"  API title : {api_title[:80]}...")
                authors_cr = result.get("author", [])
                if authors_cr:
                    names = [
                        f"{a.get('family', '')}, {a.get('given', '')}"
                        for a in authors_cr[:3]
                    ]
                    print(f"  Authors   : {'; '.join(names)}...")

        # Try CrossRef for non-arXiv DOIs that also have arXiv DOIs
        if not api_title and doi and doi.startswith("10.48550/arXiv"):
            if not arxiv_match:
                print(f"  DOI       : {doi}")
                print("  SKIP      : arXiv DOI but no arXiv ID extracted")

        # For URL-only entries
        if not api_title and url and not doi:
            print(f"  URL       : {url}")
            print("  NOTE      : No DOI, URL-only entry — manual check needed")

        # Verdict
        if api_title:
            match, detail = compare_titles(bib_title, api_title)
            if match:
                print(f"  RESULT    : OK ({verified_via}, {detail})")
                ok_count += 1
            else:
                print(f"  RESULT    : MISMATCH ({verified_via}, {detail})")
                print(f"  >>> BIB: {normalize(bib_title)[:60]}")
                print(f"  >>> API: {normalize(api_title)[:60]}")
                warn_count += 1
        else:
            if url and not doi:
                print("  RESULT    : MANUAL CHECK NEEDED (no DOI)")
                warn_count += 1
            else:
                print("  RESULT    : FAILED TO VERIFY (API returned nothing)")
                fail_count += 1

        time.sleep(0.5)

    print("\n" + "=" * 90)
    print(
        f"\nSUMMARY: {ok_count} OK / {warn_count} WARN / {fail_count} FAIL / {len(entries)} TOTAL"
    )


if __name__ == "__main__":
    import sys

    bib_file = sys.argv[1] if len(sys.argv) > 1 else "refs.bib"
    main(bib_file)
