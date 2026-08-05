"""Judge-vs-human agreement for the LLM-as-judge evaluation.

After you fill the ``human_verdict`` column (PASS / FAIL) in the manual-review
CSV produced by ``judge_responses.py`` (``agents_evaluation/output/agent_judge_review.csv``),
this script measures how well the ``gemini-2.5-pro`` judge agrees with your
verdicts: raw percent agreement and Cohen's kappa, per dependency and overall.
It gives the memoria a single reliability figure for the automatic judge.

Rows with an empty (or non PASS/FAIL) ``human_verdict`` are ignored, as are rows
whose ``judge_overall`` is not PASS/FAIL (e.g. ERROR rows). Cohen's kappa is
computed by hand over the two categories {PASS, FAIL} - no external deps.

Outputs ``agents_evaluation/output/agent_judge_agreement.csv`` and prints the
table to the console.

Usage:
  python agents_evaluation/judge_agreement.py
  python agents_evaluation/judge_agreement.py --review path/to/agent_judge_review.csv
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

OUT_DIR = Path("agents_evaluation/output")
REVIEW_CSV = OUT_DIR / "agent_judge_review.csv"
AGREEMENT_CSV = OUT_DIR / "agent_judge_agreement.csv"

ORDER = ["DEL", "GND", "TWR"]
LABELS = ("PASS", "FAIL")


def _norm(v: str) -> str:
    return (v or "").strip().upper()


def cohen_kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's kappa over 2 raters (judge, human) with categories {PASS, FAIL}.

    kappa = (po - pe) / (1 - pe), where po is observed agreement and pe is the
    agreement expected by chance from each rater's marginal label frequencies.
    Returns 1.0 when there is no room for disagreement (pe == 1).
    """
    n = len(pairs)
    if n == 0:
        return 0.0
    po = sum(1 for a, b in pairs if a == b) / n
    pe = 0.0
    for label in LABELS:
        p_judge = sum(1 for a, _ in pairs if a == label) / n
        p_human = sum(1 for _, b in pairs if b == label) / n
        pe += p_judge * p_human
    if pe >= 1.0:
        # Both raters used a single label everywhere: perfect if they agree.
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1 - pe)


def load_pairs(path: Path) -> list[dict]:
    """Rows with a usable (judge_overall, human_verdict) pair, PASS/FAIL only."""
    rows: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            judge = _norm(r.get("judge_overall", ""))
            human = _norm(r.get("human_verdict", ""))
            if judge not in LABELS or human not in LABELS:
                continue
            rows.append({"dep": _norm(r.get("dep", "")), "judge": judge, "human": human})
    return rows


def summarise(rows: list[dict], scope: str) -> dict:
    sub = rows if scope == "TOTAL" else [r for r in rows if r["dep"] == scope]
    pairs = [(r["judge"], r["human"]) for r in sub]
    n = len(pairs)
    agree = sum(1 for a, b in pairs if a == b)
    return {
        "dep": scope,
        "n": n,
        "agree": agree,
        "agree_pct": round(100.0 * agree / n, 1) if n else 0.0,
        "cohen_kappa": round(cohen_kappa(pairs), 3) if n else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--review", default=str(REVIEW_CSV), help=f"Manual-review CSV (default {REVIEW_CSV}).")
    ap.add_argument("--out", default=str(AGREEMENT_CSV), help=f"Output CSV (default {AGREEMENT_CSV}).")
    args = ap.parse_args()

    review_path = Path(args.review)
    if not review_path.exists():
        print(f"Review CSV not found: {review_path}")
        return 1

    rows = load_pairs(review_path)
    if not rows:
        print("No rows with both judge_overall and human_verdict in {PASS, FAIL}.")
        print("Fill the 'human_verdict' column in the review CSV first.")
        return 1

    scopes = [d for d in ORDER if any(r["dep"] == d for r in rows)] + ["TOTAL"]
    results = [summarise(rows, s) for s in scopes]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["dep", "n", "agree", "agree_pct", "cohen_kappa"])
        w.writeheader()
        w.writerows(results)
    print(f"Wrote: {out_path}\n")

    print(f"{'Dep':<6} {'n':>4} {'agree':>6} {'agree%':>8} {'kappa':>7}")
    print("-" * 34)
    for r in results:
        print(f"{r['dep']:<6} {r['n']:>4} {r['agree']:>6} {r['agree_pct']:>7.1f}% {r['cohen_kappa']:>7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
