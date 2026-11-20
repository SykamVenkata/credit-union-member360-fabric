"""Member identity resolution across core banking, insurance and investment systems.

The three systems share no key. Records are standardized, compared only within
blocks (shared email, phone, or DOB + last-name sound), matched with explainable
rules, and clustered with union-find. Each cluster gets one golden member id.

Rules are deliberately conservative: a false merge shows one member another
person's accounts (a privacy incident), while a missed merge only means a weaker
Member 360. So DOB conflicts veto any match, and name similarity alone never
merges two records.
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from difflib import SequenceMatcher
from itertools import combinations

NICKNAMES = {
    "jim": "james", "jimmy": "james", "bob": "robert", "rob": "robert", "bobby": "robert",
    "pat": "patricia", "mike": "michael", "jen": "jennifer", "jenny": "jennifer",
    "bill": "william", "will": "william", "liz": "elizabeth", "beth": "elizabeth",
    "rick": "richard", "dick": "richard", "sue": "susan", "joe": "joseph", "tom": "thomas",
    "chris": "christopher", "dan": "daniel", "danny": "daniel", "matt": "matthew",
    "tony": "anthony", "maggie": "margaret", "peggy": "margaret", "sam": "samuel",
}


@dataclass
class Record:
    system: str
    record_id: str
    first: str = ""
    last: str = ""
    dob: str = ""          # ISO yyyy-mm-dd or ""
    email: str = ""
    phone: str = ""        # last 10 digits or ""
    zip: str = ""
    raw: dict = field(default_factory=dict, repr=False)


# ── Standardization ─────────────────────────────────────────────────────────

def _ascii(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()


def norm_name(s: str) -> str:
    return re.sub(r"[^a-z]", "", _ascii(s).lower())


def canonical_first(s: str) -> str:
    n = norm_name(s)
    return NICKNAMES.get(n, n)


def norm_email(s: str) -> str:
    s = (s or "").strip().lower()
    return s if re.fullmatch(r"[^@\s]+@[^@\s]+\.[a-z]+", s) else ""


def norm_phone(s: str) -> str:
    digits = re.sub(r"\D", "", s or "")
    return digits[-10:] if len(digits) >= 10 else ""


def norm_dob(s: str) -> str:
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return ""


def soundex(name: str) -> str:
    n = norm_name(name).upper()
    if not n:
        return ""
    codes = {c: str(d) for d, letters in enumerate(["AEIOUYHW", "BFPV", "CGJKQSXZ", "DT", "L", "MN", "R"])
             for c in letters}
    out, prev = n[0], codes.get(n[0], "")
    for c in n[1:]:
        code = codes.get(c, "")
        if code not in ("0", prev) and code:
            out += code
        if c not in "HW":
            prev = code
    return (out + "000")[:4]


def from_core(r: dict) -> Record:
    return Record("core", r["member_id"], canonical_first(r["first_name"]), norm_name(r["last_name"]),
                  norm_dob(r["date_of_birth"]), norm_email(r["email"]), norm_phone(r["phone"]), r.get("zip", ""), r)


def from_insurance(r: dict) -> Record:
    parts = (r["full_name"] or "").split()
    first, last = (parts[0], parts[-1]) if len(parts) >= 2 else ("", parts[0] if parts else "")
    return Record("insurance", r["customer_ref"], canonical_first(first), norm_name(last),
                  norm_dob(r["date_of_birth"]), norm_email(r["email"]), norm_phone(r["phone"]), r.get("postal_code", ""), r)


def from_investments(r: dict) -> Record:
    return Record("investments", r["client_id"], canonical_first(r["first_name"]), norm_name(r["last_name"]),
                  norm_dob(r["date_of_birth"]), norm_email(r["email"]), norm_phone(r["phone"]), "", r)


# ── Blocking, matching, clustering ──────────────────────────────────────────

def blocking_keys(r: Record) -> list:
    keys = []
    if r.email:
        keys.append(f"email:{r.email}")
    if r.phone:
        keys.append(f"phone:{r.phone}")
    if r.dob and r.last:
        keys.append(f"dob_sx:{r.dob}:{soundex(r.last)}")
    return keys


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


@dataclass(frozen=True)
class Match:
    left: str
    right: str
    rule: str


def match_rule(a: Record, b: Record):
    """Return the name of the rule that matches a and b, or None. Order matters: veto first."""
    if a.dob and b.dob and a.dob != b.dob:
        return None
    last_sim = similarity(a.last, b.last)
    first_ok = a.first == b.first or similarity(a.first, b.first) >= 0.8
    if a.email and a.email == b.email and (first_ok or last_sim >= 0.85):
        return "email+name"
    if a.phone and a.phone == b.phone and a.dob and a.dob == b.dob:
        return "phone+dob"
    if a.phone and a.phone == b.phone and first_ok and last_sim >= 0.85:
        return "phone+name"
    if a.dob and a.dob == b.dob and first_ok and last_sim >= 0.85 and a.zip and a.zip == b.zip:
        return "dob+name+zip"
    return None


class UnionFind:
    def __init__(self):
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def key(r: Record) -> str:
    return f"{r.system}:{r.record_id}"


def resolve(records: list, max_block: int = 50):
    """Return (identity_map rows, matches). identity_map: system, record_id, golden_id, rule."""
    blocks = defaultdict(list)
    for r in records:
        for k in blocking_keys(r):
            blocks[k].append(r)

    uf, matches, seen = UnionFind(), [], set()
    for r in records:
        uf.find(key(r))
    for members in blocks.values():
        if len(members) > max_block:  # shared family email / call-center phone: too generic to trust
            continue
        for a, b in combinations(members, 2):
            pair = tuple(sorted((key(a), key(b))))
            if pair in seen:
                continue
            seen.add(pair)
            rule = match_rule(a, b)
            if rule:
                uf.union(*pair)
                matches.append(Match(*pair, rule))

    clusters = defaultdict(list)
    for r in records:
        clusters[uf.find(key(r))].append(r)

    rows = []
    for members in clusters.values():
        core_ids = sorted(m.record_id for m in members if m.system == "core")
        golden = core_ids[0] if core_ids else "PROSPECT-" + sorted(key(m) for m in members)[0].split(":", 1)[1]
        for m in members:
            rows.append(dict(system=m.system, record_id=m.record_id, golden_id=golden,
                             is_member=bool(core_ids), cluster_size=len(members)))
    return rows, matches


def evaluate(identity_rows: list, truth_rows: list) -> dict:
    """Pairwise precision / recall of the resolved clusters against ground truth."""
    def pairs(assign: dict) -> set:
        groups = defaultdict(list)
        for k, g in assign.items():
            groups[g].append(k)
        return {tuple(sorted(p)) for g in groups.values() for p in combinations(g, 2)}

    predicted = pairs({f"{r['system']}:{r['record_id']}": r["golden_id"] for r in identity_rows})
    actual = pairs({f"{r['system']}:{r['record_id']}": r["person_id"] for r in truth_rows})
    tp = len(predicted & actual)
    precision = tp / len(predicted) if predicted else 1.0
    recall = tp / len(actual) if actual else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"pairs_true": len(actual), "pairs_predicted": len(predicted), "true_positive": tp,
            "precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
