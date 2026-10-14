#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urljoin, urlsplit, urlunsplit


REDIRECT_CODES = {301, 302, 303, 307, 308}


@dataclass
class Rule:
    source: str
    status: int
    origin: str
    matcher: Callable[[str], tuple[bool, str]]


def absolute(current: str, target: str) -> str:
    return urljoin(current, target)


def path_of(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    if parsed.query:
        return path + "?" + parsed.query
    return path


def apache_rules(path: Path) -> list[Rule]:
    rules: list[Rule] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = re.match(r"Redirect\s+(301|302|303|307|308)\s+(\S+)\s+(\S+)", line, re.I)
        if m:
            status = int(m.group(1))
            src = m.group(2)
            dst = m.group(3)

            def make(src=src, dst=dst):
                def matcher(url: str):
                    p = urlsplit(url).path or "/"
                    if p == src or p.startswith(src.rstrip("/") + "/"):
                        suffix = p[len(src):] if p.startswith(src) else ""
                        target = dst + suffix
                        return True, absolute(url, target)
                    return False, url
                return matcher

            rules.append(Rule(line, status, "apache", make()))
            continue

        m = re.match(r"RewriteRule\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]", line, re.I)
        if m:
            pattern, dst, flags = m.groups()
            code_match = re.search(r"R(?:=(301|302|303|307|308))?", flags, re.I)
            if not code_match:
                continue
            status = int(code_match.group(1) or 302)
            regex = re.compile(pattern)

            def make(regex=regex, dst=dst):
                def matcher(url: str):
                    p = (urlsplit(url).path or "/").lstrip("/")
                    mm = regex.search(p)
                    if not mm:
                        return False, url
                    target = dst
                    for i, val in enumerate(mm.groups(), start=1):
                        target = target.replace(f"${i}", val or "")
                    return True, absolute(url, target)
                return matcher

            rules.append(Rule(line, status, "apache", make()))
    return rules


def nginx_rules(path: Path) -> list[Rule]:
    rules: list[Rule] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        m = re.search(r"rewrite\s+(\S+)\s+(\S+)\s+(permanent|redirect);", line, re.I)
        if m:
            pattern, dst, kind = m.groups()
            status = 301 if kind.lower() == "permanent" else 302
            regex = re.compile(pattern)

            def make(regex=regex, dst=dst):
                def matcher(url: str):
                    p = urlsplit(url).path or "/"
                    mm = regex.search(p)
                    if not mm:
                        return False, url
                    target = dst
                    for i, val in enumerate(mm.groups(), start=1):
                        target = target.replace(f"${i}", val or "")
                    return True, absolute(url, target)
                return matcher

            rules.append(Rule(line, status, "nginx", make()))
            continue

        m = re.search(r"return\s+(301|302|303|307|308)\s+(\S+);", line, re.I)
        if m:
            status = int(m.group(1))
            dst = m.group(2)

            def make(dst=dst):
                def matcher(url: str):
                    return True, absolute(url, dst)
                return matcher

            rules.append(Rule(line, status, "nginx", make()))
    return rules


def cloudflare_rules(path: Path) -> list[Rule]:
    rules: list[Rule] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        src, dst, code = parts[:3]
        try:
            status = int(code)
        except ValueError:
            continue
        if status not in REDIRECT_CODES:
            continue

        wildcard = "*" in src
        if wildcard:
            prefix, suffix = src.split("*", 1)

            def make(prefix=prefix, suffix=suffix, dst=dst):
                def matcher(url: str):
                    p = urlsplit(url).path or "/"
                    if not p.startswith(prefix):
                        return False, url
                    if suffix and not p.endswith(suffix):
                        return False, url
                    middle_end = len(p) - len(suffix) if suffix else len(p)
                    splat = p[len(prefix):middle_end]
                    target = dst.replace(":splat", splat)
                    return True, absolute(url, target)
                return matcher
        else:
            def make(src=src, dst=dst):
                def matcher(url: str):
                    p = urlsplit(url).path or "/"
                    if p != src:
                        return False, url
                    return True, absolute(url, dst)
                return matcher

        rules.append(Rule(line, status, "cloudflare", make()))
    return rules


def normalize(url: str) -> str:
    parsed = urlsplit(url)
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, parsed.query, ""))


def simulate(start: str, rules: Iterable[Rule], max_hops: int = 20) -> tuple[list[tuple[int, str, str]], str, bool]:
    current = normalize(start)
    seen = {current}
    chain: list[tuple[int, str, str]] = []

    for _ in range(max_hops):
        matched = False
        for rule in rules:
            ok, target = rule.matcher(current)
            if not ok:
                continue
            target = normalize(target)
            chain.append((rule.status, rule.origin, target))
            current = target
            matched = True
            if current in seen:
                return chain, current, True
            seen.add(current)
            break
        if not matched:
            return chain, current, False

    return chain, current, True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate Apache, Nginx and Cloudflare redirect rules before deployment."
    )
    parser.add_argument("url", help="URL to simulate")
    parser.add_argument("--apache", type=Path)
    parser.add_argument("--nginx", type=Path)
    parser.add_argument("--cloudflare", type=Path)
    parser.add_argument("--max-hops", type=int, default=20)
    args = parser.parse_args()

    rules: list[Rule] = []
    if args.apache:
        rules.extend(apache_rules(args.apache))
    if args.nginx:
        rules.extend(nginx_rules(args.nginx))
    if args.cloudflare:
        rules.extend(cloudflare_rules(args.cloudflare))

    print(f"START  {normalize(args.url)}")
    chain, final_url, loop = simulate(args.url, rules, args.max_hops)
    for status, origin, target in chain:
        print(f"{status:<6} {origin:<11} {target}")

    if loop:
        print(f"LOOP   {final_url}")
        return 2

    print(f"END    {final_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
