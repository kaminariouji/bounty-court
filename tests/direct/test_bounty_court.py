"""Direct-mode tests for BountyCourt v3.

Each test tries to break one rule that protects the verdict. The v3 rules are
narrower than v2 on purpose: the contract may only act on the verdict and the
band, never on the numeric score, because the equivalence rule lets accepted
scores differ inside one band.
"""

import json

from tests.direct.conftest import to_hex

CONTRACT = "contracts/bounty_court.py"

RUBRIC = (
    "The deliverable must (1) state a concrete thesis, (2) cite at least one "
    "primary source, (3) be at least 300 words, (4) contain no unsupported "
    "numeric claims."
)


def _bounty(contract, min_score=60):
    return contract.create_bounty(
        "Explain why agent escrow fails without adjudication",
        RUBRIC,
        "2026-10-30",
        min_score,
    )


def _band_of(score):
    if score >= 75:
        return "strong"
    if score >= 50:
        return "adequate"
    if score >= 25:
        return "weak"
    return "unusable"


def _mock_adjudication(vm, score, verdict, missing="", band=None):
    # The harness keeps the first mock that matches, so a second round needs a reset.
    vm.clear_mocks()
    vm.mock_web(
        r".*example\.com.*",
        {"status": 200, "body": "A long deliverable body. " * 40},
    )
    vm.mock_llm(
        r".*adjudicating a bounty submission.*",
        json.dumps(
            {
                "score": score,
                "band": band if band is not None else _band_of(score),
                "verdict": verdict,
                "missing": missing,
            }
        ),
    )


def test_create_bounty_stores_rubric(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract)
    b = contract.get_bounty(bounty_id)
    assert b["rubric"] == RUBRIC
    assert b["min_score"] == 60
    assert b["min_band"] == "adequate"
    assert b["status"] == "open"
    assert b["poster"] == to_hex(direct_alice)
    assert b["best_submission"] == ""
    assert b["best_band"] == ""
    assert b["best_rank"] == 0


def test_min_score_is_floored_to_a_band_edge(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    assert contract.get_bounty(_bounty(contract, 1))["min_band"] == "unusable"
    assert contract.get_bounty(_bounty(contract, 26))["min_band"] == "weak"
    assert contract.get_bounty(_bounty(contract, 74))["min_band"] == "adequate"
    assert contract.get_bounty(_bounty(contract, 100))["min_band"] == "strong"


def test_create_bounty_rejects_short_rubric(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Rubric too short to adjudicate"):
        contract.create_bounty("Too vague", "be good", "2026-10-30", 60)


def test_create_bounty_rejects_out_of_range_score(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("min_score must be 0-100"):
        contract.create_bounty("Title", RUBRIC, "2026-10-30", 140)


def test_create_bounty_rejects_oversized_rubric(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Rubric too long"):
        contract.create_bounty("Title", "x" * 4001, "2026-10-30", 60)


def test_submit_deliverable_indexes_submission(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract)
    direct_vm.sender = direct_bob
    sub_id = contract.submit_deliverable(bounty_id, "https://example.com/writeup", "first pass")
    s = contract.get_submission(sub_id)
    assert s["bounty_id"] == bounty_id
    assert s["worker"] == to_hex(direct_bob)
    assert s["verdict"] == ""
    assert s["judged"] is False
    assert contract.list_submissions(bounty_id) == [sub_id]


def test_submit_rejects_non_http(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract)
    for bad in ("ipfs://abc", "httpfoo", "ftp://x"):
        with direct_vm.expect_revert("Deliverable must be an http(s) URL"):
            contract.submit_deliverable(bounty_id, bad, "note")


def test_submit_caps_submissions_per_worker(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract)
    direct_vm.sender = direct_bob
    for i in range(3):
        contract.submit_deliverable(bounty_id, "https://example.com/%d" % i, "")
    with direct_vm.expect_revert("Submission limit reached for this worker"):
        contract.submit_deliverable(bounty_id, "https://example.com/fourth", "")
    direct_vm.sender = direct_alice
    contract.submit_deliverable(bounty_id, "https://example.com/alice", "")


def test_adjudicate_pass_above_threshold(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract, min_score=60)
    direct_vm.sender = direct_bob
    sub_id = contract.submit_deliverable(bounty_id, "https://example.com/a", "")
    _mock_adjudication(direct_vm, 88, "pass")
    assert contract.adjudicate(sub_id) == "pass"
    s = contract.get_submission(sub_id)
    assert s["score"] == 88
    assert s["band"] == "strong"
    b = contract.get_bounty(bounty_id)
    assert b["best_submission"] == sub_id
    assert b["best_band"] == "strong"
    assert b["best_rank"] == 3


def test_adjudicate_fails_when_band_below_threshold(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract, min_score=75)
    direct_vm.sender = direct_bob
    sub_id = contract.submit_deliverable(bounty_id, "https://example.com/b", "")
    _mock_adjudication(direct_vm, 55, "pass", "no primary source")
    assert contract.adjudicate(sub_id) == "fail"
    s = contract.get_submission(sub_id)
    assert s["score"] == 55
    assert s["band"] == "adequate"
    assert s["missing"] == "no primary source"
    assert contract.get_bounty(bounty_id)["best_submission"] == ""


def test_band_not_score_decides_the_threshold(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    # 50 and 74 sit in the same band, so the same minimum must treat them alike.
    # Under a raw threshold of 60 the first would fail and the second pass; under
    # a band threshold both pass. This is the property the steward asked for.
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract, min_score=60)
    direct_vm.sender = direct_bob
    low = contract.submit_deliverable(bounty_id, "https://example.com/low", "")
    _mock_adjudication(direct_vm, 50, "pass")
    assert contract.adjudicate(low) == "pass"
    high = contract.submit_deliverable(bounty_id, "https://example.com/high", "")
    _mock_adjudication(direct_vm, 74, "pass")
    assert contract.adjudicate(high) == "pass"


def test_adjudicate_fails_on_verdict(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract, min_score=40)
    direct_vm.sender = direct_bob
    sub_id = contract.submit_deliverable(bounty_id, "https://example.com/c", "")
    _mock_adjudication(direct_vm, 95, "fail", "claims are unsupported")
    assert contract.adjudicate(sub_id) == "fail"


def test_best_submission_only_moves_up_a_band(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract, min_score=50)
    direct_vm.sender = direct_bob
    low = contract.submit_deliverable(bounty_id, "https://example.com/low", "")
    _mock_adjudication(direct_vm, 70, "pass")
    contract.adjudicate(low)
    assert contract.get_bounty(bounty_id)["best_submission"] == low
    high = contract.submit_deliverable(bounty_id, "https://example.com/high", "")
    _mock_adjudication(direct_vm, 92, "pass")
    contract.adjudicate(high)
    assert contract.get_bounty(bounty_id)["best_submission"] == high
    assert contract.get_bounty(bounty_id)["best_band"] == "strong"
    direct_vm.sender = direct_alice
    weaker = contract.submit_deliverable(bounty_id, "https://example.com/weaker", "")
    _mock_adjudication(direct_vm, 60, "pass")
    contract.adjudicate(weaker)
    assert contract.get_bounty(bounty_id)["best_submission"] == high


def test_equal_band_goes_to_the_earlier_submission(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    # Adjudication order must not decide the winner: judge the later submission
    # first with a higher raw score, then the earlier one in the same band.
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract, min_score=50)
    direct_vm.sender = direct_bob
    first = contract.submit_deliverable(bounty_id, "https://example.com/first", "")
    second = contract.submit_deliverable(bounty_id, "https://example.com/second", "")
    _mock_adjudication(direct_vm, 92, "pass")
    contract.adjudicate(second)
    assert contract.get_bounty(bounty_id)["best_submission"] == second
    _mock_adjudication(direct_vm, 76, "pass")
    contract.adjudicate(first)
    b = contract.get_bounty(bounty_id)
    assert b["best_submission"] == first
    assert b["best_rank"] == 3


def test_raw_score_cannot_break_a_band_tie(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    # 60 and 74 are both "adequate". The earlier submission keeps the slot even
    # though the later one has the higher number, because the number is the part
    # validators are allowed to disagree on.
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract, min_score=50)
    direct_vm.sender = direct_bob
    first = contract.submit_deliverable(bounty_id, "https://example.com/first", "")
    _mock_adjudication(direct_vm, 60, "pass")
    contract.adjudicate(first)
    second = contract.submit_deliverable(bounty_id, "https://example.com/second", "")
    _mock_adjudication(direct_vm, 74, "pass")
    contract.adjudicate(second)
    assert contract.get_bounty(bounty_id)["best_submission"] == first


def test_malformed_band_falls_back_to_the_score(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract, min_score=75)
    direct_vm.sender = direct_bob
    sub_id = contract.submit_deliverable(bounty_id, "https://example.com/g", "")
    _mock_adjudication(direct_vm, 80, "pass", band="excellent")
    assert contract.adjudicate(sub_id) == "pass"
    assert contract.get_submission(sub_id)["band"] == "strong"


def test_adjudicate_twice_reverts(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract)
    direct_vm.sender = direct_bob
    sub_id = contract.submit_deliverable(bounty_id, "https://example.com/d", "")
    _mock_adjudication(direct_vm, 80, "pass")
    contract.adjudicate(sub_id)
    with direct_vm.expect_revert("Already adjudicated"):
        contract.adjudicate(sub_id)


def test_closed_bounty_refuses_new_submissions_and_judging(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract)
    direct_vm.sender = direct_bob
    sub_id = contract.submit_deliverable(bounty_id, "https://example.com/e", "")
    direct_vm.sender = direct_alice
    contract.close_bounty(bounty_id)
    assert contract.get_bounty(bounty_id)["status"] == "closed"
    with direct_vm.expect_revert("Bounty is not open"):
        contract.submit_deliverable(bounty_id, "https://example.com/late", "")
    with direct_vm.expect_revert("Bounty is closed"):
        contract.adjudicate(sub_id)


def test_close_bounty_is_poster_only(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract)
    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("Only the poster can close this bounty"):
        contract.close_bounty(bounty_id)


def test_unknown_ids_revert(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("Unknown bounty"):
        contract.get_bounty("b999")
    with direct_vm.expect_revert("Unknown submission"):
        contract.get_submission("s999")


def test_stats_counts_judgements(direct_vm, direct_deploy, direct_alice, direct_bob):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract)
    direct_vm.sender = direct_bob
    sub_id = contract.submit_deliverable(bounty_id, "https://example.com/f", "")
    _mock_adjudication(direct_vm, 75, "pass")
    contract.adjudicate(sub_id)
    st = contract.stats()
    assert st["bounties"] == 1
    assert st["submissions"] == 1
    assert st["judged"] == 1


def _addr(i):
    return bytes([0] * 18 + [i // 256, i % 256])


def test_bounty_total_submission_cap(direct_vm, direct_deploy, direct_alice):
    contract = direct_deploy(CONTRACT)
    direct_vm.sender = direct_alice
    bounty_id = _bounty(contract)

    for i in range(200):
        direct_vm.sender = _addr(i + 1)
        contract.submit_deliverable(bounty_id, "https://example.com/%d" % i, "")

    direct_vm.sender = _addr(201)
    with direct_vm.expect_revert("Bounty submission limit reached"):
        contract.submit_deliverable(bounty_id, "https://example.com/overflow", "")
