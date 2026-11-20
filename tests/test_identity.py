import pytest

from creditunion import identity as I


def core(mid, first="Robert", last="Smith", dob="1980-05-01", email="rob@x.com", phone="415-555-0101", zip_="94105"):
    return I.from_core(dict(member_id=mid, first_name=first, last_name=last, date_of_birth=dob,
                            email=email, phone=phone, zip=zip_))


def ins(ref, name="BOB SMITH", dob="05/01/1980", email="ROB@X.COM", phone="(415) 555-0101", zip_="94105"):
    return I.from_insurance(dict(customer_ref=ref, full_name=name, date_of_birth=dob, email=email,
                                 phone=phone, postal_code=zip_))


@pytest.mark.parametrize("raw,expected", [
    (" Rob@X.com ", "rob@x.com"), ("not-an-email", ""), ("", "")])
def test_norm_email(raw, expected):
    assert I.norm_email(raw) == expected


@pytest.mark.parametrize("raw", ["(415) 555-0101", "415-555-0101", "+14155550101", "415.555.0101"])
def test_norm_phone_formats_agree(raw):
    assert I.norm_phone(raw) == "4155550101"


def test_dob_formats_and_nicknames():
    assert I.norm_dob("05/01/1980") == I.norm_dob("1980-05-01") == "1980-05-01"
    assert I.canonical_first("Bob") == I.canonical_first("ROBERT") == "robert"
    assert I.soundex("Robert") == "R163" and I.soundex("Rupert") == "R163"


def test_same_person_across_systems_merges():
    rows, matches = I.resolve([core("M1"), ins("IC-1")])
    assert {r["golden_id"] for r in rows} == {"M1"}
    assert matches[0].rule == "email+name"


def test_dob_conflict_vetoes_even_with_same_email():
    rows, _ = I.resolve([core("M1"), ins("IC-1", dob="05/02/1980")])
    assert len({r["golden_id"] for r in rows}) == 2


def test_name_alone_never_merges():
    a = core("M1", email="a@x.com", phone="")
    b = ins("IC-1", email="b@y.com", phone="", zip_="10001")  # same name + dob, different zip
    rows, _ = I.resolve([a, b])
    assert len({r["golden_id"] for r in rows}) == 2


def test_non_member_becomes_prospect():
    rows, _ = I.resolve([core("M1"), ins("IC-9", name="Ann Lee", dob="01/01/1990", email="ann@z.com", phone="2125550000")])
    prospect = next(r for r in rows if r["record_id"] == "IC-9")
    assert not prospect["is_member"] and prospect["golden_id"].startswith("PROSPECT-")


def test_two_core_numbers_resolve_to_lowest():
    rows, _ = I.resolve([core("M000009"), core("M000002", last="Smtih")])
    assert {r["golden_id"] for r in rows} == {"M000002"}


def test_oversized_blocks_are_skipped():
    recs = [core(f"M{i}", first=f"P{i}", last=f"L{i}", dob=f"19{50 + i}-01-01", email="shared@x.com", phone="")
            for i in range(5)]
    rows, _ = I.resolve(recs, max_block=3)
    assert len({r["golden_id"] for r in rows}) == 5


def test_sample_match_quality(run_output):
    q = run_output[0]["identity"]["quality"]
    assert q["precision"] >= 0.98, "false merges expose one member's data to another"
    assert q["recall"] >= 0.95
