"""
Deterministic AS (Anomaly Score) and APS (Action Priority Score) engine.

Zero external dependencies — pure Python arithmetic.
Latency: < 1ms per record.

Formulas:
  AS  = (FI * 0.40) + (FR * 0.25) + (RE * 0.20) + (SR * 0.15)   range 1–10
  APS = AS * confidence / complexity                               range 0–10

Routing rule:
  APS >= 4.0 AND complexity >= 2  →  action.approval_needed
  else                            →  action.auto_execute
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Score component constants
# ---------------------------------------------------------------------------

# Amount thresholds in INR for complexity determination
COMPLEXITY_AUTONOMOUS = 50_000        # < Rs 50K  → complexity 1
COMPLEXITY_SLACK_APPROVAL = 200_000   # Rs 50K – 2L → complexity 2
COMPLEXITY_FINANCE_HEAD = 1_000_000   # Rs 2L – 10L → complexity 3
# > Rs 10L → complexity 5 (board-level)

# Recoverability scores by anomaly type
RECOVERABILITY_BY_TYPE: dict[str, float] = {
    "duplicate_payment": 10.0,    # Fully reversible
    "cloud_waste": 9.0,           # Can right-size
    "unused_saas": 8.5,           # Can deprovision
    "vendor_rate_anomaly": 7.0,   # Can dispute / renegotiate
    "sla_penalty_risk": 4.0,      # Partially avoidable
    "unknown": 5.0,
}

# APS routing thresholds
APS_APPROVAL_THRESHOLD = 4.0
COMPLEXITY_APPROVAL_THRESHOLD = 2


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------


def compute_financial_impact(amount: float, monthly_opex: float = 5_000_000) -> float:
    """
    FI — Financial Impact component (weight 40%).
    Ratio of anomaly amount to monthly opex, normalized to 1–10.
    Default monthly_opex: Rs 50L (typical Series B startup).
    """
    if monthly_opex <= 0:
        return 1.0
    ratio = amount / monthly_opex
    if ratio >= 0.10:
        return 10.0
    if ratio <= 0.005:
        return 1.0
    # Linear interpolation between 1 and 10
    return 1.0 + (ratio - 0.005) / (0.10 - 0.005) * 9.0


def compute_frequency_rank(occurrence_count: int) -> float:
    """
    FR — Frequency component (weight 25%).
    How many times this vendor/pattern has appeared.
    """
    if occurrence_count >= 6:
        return 10.0
    if occurrence_count <= 1:
        return 1.5
    # Score map for 2–5 occurrences
    score_map = {2: 4.0, 3: 6.0, 4: 7.5, 5: 9.0}
    return score_map.get(occurrence_count, 5.0)


def compute_recoverability(anomaly_type: str) -> float:
    """
    RE — Recoverability component (weight 20%).
    How easily the financial impact can be recovered.
    """
    return RECOVERABILITY_BY_TYPE.get(anomaly_type, RECOVERABILITY_BY_TYPE["unknown"])


def compute_severity_risk(affected_record_count: int) -> float:
    """
    SR — Systemic Risk component (weight 15%).
    Blast radius: how many records are affected.
    """
    if affected_record_count >= 50:
        return 10.0
    if affected_record_count <= 1:
        return 2.0
    # Linear interpolation between 2 and 10
    return 2.0 + (affected_record_count - 1) / (50 - 1) * 8.0


def compute_anomaly_score(
    financial_impact: float,
    frequency_rank: float,
    recoverability_ease: float,
    severity_risk: float,
) -> float:
    """
    AS — Anomaly Score.
    Weighted composite of the four dimensions. Range: 1–10.
    """
    raw = (
        financial_impact * 0.40
        + frequency_rank * 0.25
        + recoverability_ease * 0.20
        + severity_risk * 0.15
    )
    return round(min(max(raw, 1.0), 10.0), 4)


def determine_complexity(amount: float, as_score: float) -> int:
    """
    Complexity tier — determines the human approval chain.
      1 → autonomous     (amount < Rs 50K or AS < 4.0)
      2 → Slack/email    (Rs 50K – 2L)
      3 → Finance head   (Rs 2L – 10L)
      5 → Board level    (> Rs 10L)
    """
    if amount < COMPLEXITY_AUTONOMOUS or as_score < 4.0:
        return 1
    if amount < COMPLEXITY_SLACK_APPROVAL:
        return 2
    if amount < COMPLEXITY_FINANCE_HEAD:
        return 3
    return 5


def compute_action_priority_score(
    as_score: float, confidence: float, complexity: int
) -> float:
    """
    APS — Action Priority Score.
    Adjusts AS by detection confidence and approval complexity. Range: 0–10.
    """
    if complexity <= 0:
        complexity = 1
    aps = as_score * confidence / complexity
    return round(min(max(aps, 0.0), 10.0), 4)


def requires_approval(aps_score: float, complexity: int) -> bool:
    """
    Routing rule: if APS >= threshold AND complexity >= threshold → needs human approval.
    """
    return aps_score >= APS_APPROVAL_THRESHOLD and complexity >= COMPLEXITY_APPROVAL_THRESHOLD


def score_anomaly(
    amount: float,
    anomaly_type: str,
    confidence: float,
    occurrence_count: int = 1,
    affected_record_count: int = 1,
    monthly_opex: float = 5_000_000,
) -> dict:
    """
    Convenience function — runs the full scoring pipeline and returns all components.

    Returns:
        {
            financial_impact, frequency_rank, recoverability_ease, severity_risk,
            as_score, complexity, aps_score, approval_needed
        }
    """
    fi = compute_financial_impact(amount, monthly_opex)
    fr = compute_frequency_rank(occurrence_count)
    re = compute_recoverability(anomaly_type)
    sr = compute_severity_risk(affected_record_count)
    as_score = compute_anomaly_score(fi, fr, re, sr)
    complexity = determine_complexity(amount, as_score)
    aps = compute_action_priority_score(as_score, confidence, complexity)
    needs_approval = requires_approval(aps, complexity)

    return {
        "financial_impact": round(fi, 4),
        "frequency_rank": round(fr, 4),
        "recoverability_ease": round(re, 4),
        "severity_risk": round(sr, 4),
        "as_score": as_score,
        "complexity": complexity,
        "aps_score": aps,
        "approval_needed": needs_approval,
    }
