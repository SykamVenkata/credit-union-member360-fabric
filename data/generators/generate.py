"""Synthetic credit union data, shaped like extracts from four separate source systems.

    python data/generators/generate.py --members 600 --out data/sample

The systems do not share a member key, which is the point of the project:
  core banking   -> core_members, deposit_accounts, transactions, loans, digital_activity
  insurance      -> ins_customers, ins_policies, ins_claims        (own customer_ref)
  investments    -> inv_clients, inv_accounts                      (own client_id)

The same person appears with realistic variations across systems (nicknames, email
case, phone formats, typos, missing DOB), some insurance/investment customers are not
members at all, and a few people hold two core member numbers. `_identity_truth.csv`
records who is really who, so match quality can be measured. It is never read by the
pipeline itself.

Behaviour is seeded so that churn, cross-sell and AML patterns are learnable:
low-engagement members are more likely to close after the as-of date, and a handful
of accounts carry structuring and rapid-movement patterns.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

AS_OF = date(2025, 9, 30)

FIRST = [
    "James",
    "Mary",
    "Robert",
    "Patricia",
    "Michael",
    "Jennifer",
    "William",
    "Linda",
    "David",
    "Elizabeth",
    "Richard",
    "Susan",
    "Joseph",
    "Jessica",
    "Thomas",
    "Sarah",
    "Christopher",
    "Karen",
    "Daniel",
    "Nancy",
    "Matthew",
    "Lisa",
    "Anthony",
    "Margaret",
    "Priya",
    "Arjun",
    "Wei",
    "Mei",
    "Carlos",
    "Sofia",
    "Ahmed",
    "Fatima",
    "Kenji",
    "Yuki",
    "Olga",
    "Ivan",
    "Grace",
    "Samuel",
]
NICK = {
    "James": "Jim",
    "Robert": "Bob",
    "Patricia": "Pat",
    "Michael": "Mike",
    "Jennifer": "Jen",
    "William": "Bill",
    "Elizabeth": "Liz",
    "Richard": "Rick",
    "Susan": "Sue",
    "Joseph": "Joe",
    "Thomas": "Tom",
    "Christopher": "Chris",
    "Daniel": "Dan",
    "Matthew": "Matt",
    "Anthony": "Tony",
    "Margaret": "Maggie",
    "Samuel": "Sam",
}
LAST = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Rodriguez",
    "Martinez",
    "Hernandez",
    "Lopez",
    "Gonzalez",
    "Wilson",
    "Anderson",
    "Thomas",
    "Taylor",
    "Moore",
    "Jackson",
    "Martin",
    "Lee",
    "Perez",
    "Thompson",
    "White",
    "Harris",
    "Sanchez",
    "Clark",
    "Patel",
    "Nguyen",
    "Kim",
    "Chen",
    "Singh",
    "Reddy",
    "Kowalski",
    "Okafor",
    "Tanaka",
    "Murphy",
    "Rivera",
]
DOMAINS = ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "proton.me"]
BRANCHES = [
    ("B01", "Downtown", "Bay Area", "94105"),
    ("B02", "Mountain View", "Bay Area", "94040"),
    ("B03", "San Jose North", "Bay Area", "95134"),
    ("B04", "Fremont", "Bay Area", "94538"),
    ("B05", "Portland Pearl", "Pacific NW", "97209"),
    ("B06", "Beaverton", "Pacific NW", "97005"),
    ("B07", "Hillsboro", "Pacific NW", "97124"),
    ("B08", "Redmond", "Pacific NW", "98052"),
    ("B09", "Austin Domain", "Texas", "78758"),
    ("B10", "Plano", "Texas", "75024"),
    ("B11", "Irving", "Texas", "75039"),
    ("B12", "Digital Branch", "Digital", "00000"),
]
DEPOSIT_PRODUCTS = ["Rewards Checking", "Membership Savings", "Money Market", "Share Certificate", "IRA Savings"]
LOAN_PRODUCTS = ["Auto Loan", "Personal Loan", "Mortgage", "HELOC", "Credit Card", "RV Loan", "Student Loan Refi"]
INS_LINES = ["Auto", "Home", "Renters", "Life", "Umbrella"]
CHANNELS = ["Branch", "ATM", "Online", "Mobile", "Zelle", "Debit Card"]


def fmt_phone(digits: str, style: int) -> str:
    a, b, c = digits[:3], digits[3:6], digits[6:]
    return [f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"+1{digits}", f"{a}.{b}.{c}"][style]


def typo(s: str, rng: random.Random) -> str:
    if len(s) < 4:
        return s
    i = rng.randrange(1, len(s) - 1)
    return s[:i] + s[i + 1] + s[i] + s[i + 2 :]


def main(n_members: int, out: Path, seed: int) -> None:
    rng = random.Random(seed)
    used: set = set()

    def uid(prefix: str, lo: int, hi: int) -> str:
        while True:
            v = f"{prefix}{rng.randrange(lo, hi)}"
            if v not in used:
                used.add(v)
                return v

    out.mkdir(parents=True, exist_ok=True)
    rows: dict[str, list] = {
        k: []
        for k in [
            "branches",
            "core_members",
            "deposit_accounts",
            "transactions",
            "loans",
            "digital_activity",
            "ins_customers",
            "ins_policies",
            "ins_claims",
            "inv_clients",
            "inv_accounts",
            "_identity_truth",
        ]
    }
    rows["branches"] = [dict(branch_id=b, branch_name=n, region=r, zip=z) for b, n, r, z in BRANCHES]

    people = []
    for p in range(n_members):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        dob = date(1950, 1, 1) + timedelta(days=rng.randrange(0, 365 * 52))
        phone = f"{rng.randrange(200, 999)}{rng.randrange(200, 999)}{rng.randrange(1000, 9999)}"
        email = f"{first.lower()}.{last.lower()}{rng.randrange(1, 999)}@{rng.choice(DOMAINS)}"
        branch = rng.choice(BRANCHES)
        engagement = rng.betavariate(2, 2)  # hidden driver of products, activity and churn
        people.append(
            dict(pid=f"P{p:05d}", first=first, last=last, dob=dob, phone=phone, email=email, branch=branch, engagement=engagement)
        )

    mid = 0
    txn_id = loan_id = acct_id = 0
    for person in people:
        e = person["engagement"]
        mid += 1
        member_ids = [f"M{mid:06d}"]
        if rng.random() < 0.02:  # re-joined under a second member number
            mid += 1
            member_ids.append(f"M{mid:06d}")
        join = AS_OF - timedelta(days=rng.randrange(60, 365 * 15))
        young = (AS_OF - join).days < 3 * 365
        segment = "Premier" if e > 0.75 and rng.random() < 0.6 else ("Startup" if young and rng.random() < 0.4 else "Standard")
        # churn after the as-of date, driven by low engagement
        churn_p = 0.03 + 0.35 * (1 - e) ** 3
        churned = rng.random() < churn_p
        close = AS_OF + timedelta(days=rng.randrange(1, 90)) if churned else None

        for k, m in enumerate(member_ids):
            rows["core_members"].append(
                dict(
                    member_id=m,
                    first_name=person["first"],
                    last_name=person["last"] if k == 0 else typo(person["last"], rng),
                    date_of_birth=person["dob"].isoformat(),
                    email=person["email"],
                    phone=fmt_phone(person["phone"], 1),
                    zip=person["branch"][3],
                    home_branch_id=person["branch"][0],
                    segment=segment,
                    join_date=(join + timedelta(days=400 * k)).isoformat(),
                    status="Closed" if close else "Active",
                    close_date=close.isoformat() if close else "",
                    income_band=rng.choice(["<50K", "50K-75K", "75K-100K", "100K-150K", "150K+"]),
                )
            )
            rows["_identity_truth"].append(dict(system="core", record_id=m, person_id=person["pid"]))
        m = member_ids[0]

        n_dep = 1 + sum(rng.random() < e * 0.7 for _ in range(3))
        accts = []
        for prod in ["Rewards Checking", *rng.sample(DEPOSIT_PRODUCTS[1:], n_dep - 1)]:
            acct_id += 1
            bal = round(rng.lognormvariate(8 + 2.2 * e, 1.0), 2)
            a = f"D{acct_id:07d}"
            accts.append((a, bal))
            rows["deposit_accounts"].append(
                dict(account_id=a, member_id=m, product=prod, open_date=join.isoformat(), balance=bal, status="Active")
            )

        # 120 days of transactions on the checking account
        checking = accts[0][0]
        n_txn = int(5 + 80 * e * rng.random())
        for _ in range(n_txn):
            ts = datetime.combine(AS_OF, datetime.min.time()) - timedelta(minutes=rng.randrange(0, 120 * 1440))
            if close and ts > datetime.combine(AS_OF - timedelta(days=45), datetime.min.time()) and rng.random() < 0.5:
                continue  # leavers wind down activity before they close
            txn_id += 1
            channel = rng.choices(CHANNELS, weights=[2, 2, 3, 4 + 4 * e, 2 + 3 * e, 5])[0]
            amt = round(rng.lognormvariate(4, 1.1), 2) * (1 if rng.random() < 0.45 else -1)
            rows["transactions"].append(
                dict(
                    txn_id=f"T{txn_id:08d}",
                    account_id=checking,
                    ts=ts.isoformat(timespec="seconds"),
                    amount=amt,
                    channel=channel,
                    txn_type="Deposit" if amt > 0 else "Withdrawal",
                )
            )

        for _ in range(sum(rng.random() < 0.15 + 0.45 * e for _ in range(2))):
            loan_id += 1
            prod = rng.choice(LOAN_PRODUCTS)
            amt = round(rng.lognormvariate(10 if prod in ("Mortgage", "HELOC") else 8.8, 0.6), -2)
            dpd = rng.choices([0, 15, 30, 60, 90, 120], weights=[88 + 10 * e, 4, 3, 2, 1.5, 1.5])[0]
            rows["loans"].append(
                dict(
                    loan_id=f"L{loan_id:07d}",
                    member_id=m,
                    product=prod,
                    orig_date=(AS_OF - timedelta(days=rng.randrange(30, 2000))).isoformat(),
                    orig_amount=amt,
                    balance=round(amt * rng.uniform(0.2, 0.95), 2),
                    rate=round(rng.uniform(0.04, 0.19), 4),
                    days_past_due=dpd,
                )
            )

        for month in range(1, 10):
            logins = max(0, int(rng.gauss(18 * e, 4) * (0.6 if close and month >= 7 else 1)))
            rows["digital_activity"].append(
                dict(
                    member_id=m,
                    month=f"2025-{month:02d}",
                    logins=logins,
                    mobile_share=round(min(1, max(0, rng.gauss(0.4 + 0.5 * e, 0.15))), 2),
                    zelle_payments=int(logins * rng.uniform(0, 0.4)),
                )
            )

        # insurance platform: same person, messier identity
        if rng.random() < 0.15 + 0.4 * e:
            ref = uid("IC-", 10**6, 9 * 10**6)
            first = NICK.get(person["first"], person["first"]) if rng.random() < 0.4 else person["first"]
            rows["ins_customers"].append(
                dict(
                    customer_ref=ref,
                    full_name=f"{first} {person['last']}".upper() if rng.random() < 0.5 else f"{first} {person['last']}",
                    date_of_birth=person["dob"].strftime("%m/%d/%Y"),
                    email=(
                        f"{person['first'][0].lower()}{person['last'].lower()}@work-mail.com"
                        if rng.random() < 0.3
                        else person["email"].upper()
                        if rng.random() < 0.3
                        else person["email"]
                    ),
                    phone=fmt_phone(person["phone"], rng.randrange(4)) if rng.random() > 0.1 else "",
                    postal_code=person["branch"][3],
                )
            )
            rows["_identity_truth"].append(dict(system="insurance", record_id=ref, person_id=person["pid"]))
            for line in rng.sample(INS_LINES, 1 + (rng.random() < 0.3)):
                pol = uid("POL", 10**7, 9 * 10**7)
                prem = round(rng.uniform(300, 2400), 2)
                rows["ins_policies"].append(
                    dict(
                        policy_id=pol,
                        customer_ref=ref,
                        line=line,
                        annual_premium=prem,
                        status="Lapsed" if rng.random() < 0.12 else "Active",
                        start_date=(AS_OF - timedelta(days=rng.randrange(30, 1800))).isoformat(),
                    )
                )
                if rng.random() < 0.18:
                    rows["ins_claims"].append(
                        dict(
                            claim_id=uid("CLM", 10**7, 10**8),
                            policy_id=pol,
                            loss_date=(AS_OF - timedelta(days=rng.randrange(1, 365))).isoformat(),
                            paid_amount=round(rng.lognormvariate(7.5, 1), 2),
                        )
                    )

        # investment platform: email + phone, DOB often missing
        if rng.random() < 0.05 + 0.35 * e**2:
            cid = uid("INV", 10**5, 10**6)
            rows["inv_clients"].append(
                dict(
                    client_id=cid,
                    first_name=person["first"],
                    last_name=person["last"] if rng.random() > 0.1 else typo(person["last"], rng),
                    email=(
                        f"{person['last'].lower()}.{person['first'].lower()}@icloud.com"
                        if rng.random() < 0.25
                        else f"  {person['email']} "
                        if rng.random() < 0.2
                        else person["email"]
                    ),
                    phone=fmt_phone(person["phone"], rng.randrange(4)) if rng.random() > 0.15 else "",
                    date_of_birth=person["dob"].isoformat() if rng.random() < 0.6 else "",
                )
            )
            rows["_identity_truth"].append(dict(system="investments", record_id=cid, person_id=person["pid"]))
            robo = rng.random() < 0.4
            rows["inv_accounts"].append(
                dict(
                    account_id=uid("IA", 10**6, 10**7),
                    client_id=cid,
                    account_type="Robo" if robo else rng.choice(["Brokerage", "Roth IRA", "Traditional IRA"]),
                    aum=round(rng.lognormvariate(10 + e, 1), 2),
                    advisor_id="" if robo else f"ADV{rng.randrange(1, 15):02d}",
                )
            )

    # non-members on the insurance/investment platforms (must not be merged into anyone)
    for k in range(n_members // 12):
        first, last = rng.choice(FIRST), rng.choice(LAST)
        dob = date(1950, 1, 1) + timedelta(days=rng.randrange(0, 365 * 52))
        ref = f"IC-{9 * 10**6 + k}"
        rows["ins_customers"].append(
            dict(
                customer_ref=ref,
                full_name=f"{first} {last}",
                date_of_birth=dob.strftime("%m/%d/%Y"),
                email=f"{first.lower()}{k}@{rng.choice(DOMAINS)}",
                phone=fmt_phone(f"{rng.randrange(200, 999)}555{rng.randrange(1000, 9999)}", 0),
                postal_code=rng.choice(BRANCHES)[3],
            )
        )
        rows["ins_policies"].append(
            dict(
                policy_id=f"POL9{k:07d}",
                customer_ref=ref,
                line="Auto",
                annual_premium=round(rng.uniform(500, 1500), 2),
                status="Active",
                start_date=(AS_OF - timedelta(days=rng.randrange(30, 900))).isoformat(),
            )
        )
        rows["_identity_truth"].append(dict(system="insurance", record_id=ref, person_id=f"X{k:05d}"))

    # AML typologies on a few checking accounts
    checking_accounts = [r["account_id"] for r in rows["deposit_accounts"] if r["product"] == "Rewards Checking"]
    for acct in rng.sample(checking_accounts, max(3, n_members // 150)):  # structuring
        start = datetime.combine(AS_OF, datetime.min.time()) - timedelta(days=rng.randrange(5, 100))
        for _ in range(rng.randrange(3, 5)):
            txn_id += 1
            rows["transactions"].append(
                dict(
                    txn_id=f"T{txn_id:08d}",
                    account_id=acct,
                    ts=(start + timedelta(hours=rng.randrange(0, 70))).isoformat(timespec="seconds"),
                    amount=round(rng.uniform(9000, 9900), 2),
                    channel="Branch",
                    txn_type="Cash Deposit",
                )
            )
    for acct in rng.sample(checking_accounts, max(3, n_members // 150)):  # rapid in / out
        t0 = datetime.combine(AS_OF, datetime.min.time()) - timedelta(days=rng.randrange(5, 100))
        amt = round(rng.uniform(15000, 40000), 2)
        for ts, a, ch, tt in [
            (t0, amt, "Online", "Wire In"),
            (t0 + timedelta(hours=rng.randrange(2, 30)), -round(amt * 0.97, 2), "Zelle", "Transfer Out"),
        ]:
            txn_id += 1
            rows["transactions"].append(
                dict(
                    txn_id=f"T{txn_id:08d}",
                    account_id=acct,
                    ts=ts.isoformat(timespec="seconds"),
                    amount=a,
                    channel=ch,
                    txn_type=tt,
                )
            )

    for name, data in rows.items():
        rng.shuffle(data) if name.startswith(("ins_", "inv_")) else None
        with open(out / f"{name}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
        print(f"{name:<18} {len(data):>7}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--members", type=int, default=800)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "sample")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    main(a.members, a.out, a.seed)
