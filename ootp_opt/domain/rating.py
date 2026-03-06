from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class RatingWeights:
    """Weights for a basic hitter rating score.

    MVP: keep it simple. Later this becomes presets/eras + PT vs franchise split.
    """
    contact: float = 1.0
    power: float = 1.2
    eye: float = 0.8

@dataclass(frozen=True)
class PitcherRatingWeights:
    stuff: float = 1.25
    movement: float = 1.10
    control: float = 1.00
    pbabip: float = 0.25
    hr_rate: float = 0.35


def rate_hitters_basic(df: pd.DataFrame, weights: RatingWeights = RatingWeights()) -> pd.DataFrame:
    """Compute a simple overall score from normalized columns.

    Expects normalized columns:
      - name (str)
      - position (str, optional)
      - contact (numeric)
      - power (numeric)
      - eye (numeric)

    Returns a copy with a new column: score_overall
    """
    required = ["name", "contact", "power", "eye"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"rate_hitters_basic() missing required columns: {missing}")

    scored = df.copy()

    # Ensure numeric (coerce errors to NaN, then fill with 0 for MVP)
    for c in ["contact", "power", "eye"]:
        scored[c] = pd.to_numeric(scored[c], errors="coerce").fillna(0)

    scored["score_overall"] = (
        scored["contact"] * weights.contact
        + scored["power"] * weights.power
        + scored["eye"] * weights.eye
    )

    return scored

def rate_pitchers_basic(df: pd.DataFrame, weights: PitcherRatingWeights = PitcherRatingWeights()) -> pd.DataFrame:
    """Simple pitcher score from normalized columns."""
    required = ["name", "stuff", "movement", "control", "pbabip", "hr_rate"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"rate_pitchers_basic() missing required columns: {missing}")

    scored = df.copy()
    for c in ["stuff", "movement", "control", "pbabip", "hr_rate"]:
        scored[c] = pd.to_numeric(scored[c], errors="coerce").fillna(0)

    scored["score_overall"] = (
        scored["stuff"] * weights.stuff
        + scored["movement"] * weights.movement
        + scored["control"] * weights.control
        + scored["pbabip"] * weights.pbabip
        + scored["hr_rate"] * weights.hr_rate
    )
    return scored

@dataclass(frozen=True)
class PitcherRoleWeights:
    # Base components (apply to both SP/RP)
    stuff: float = 1.30
    movement: float = 1.10
    control: float = 1.00
    pbabip: float = 0.30
    hr_rate: float = 0.40

    # Starter-only modifiers
    stamina: float = 0.35
    pitch_count: float = 8.0        # points per "good" pitch
    pitch_threshold: float = 60.0   # pitch rating counted as "good"
    starter_min_stamina: float = 60.0
    starter_stamina_gate_penalty: float = 1_000_000.0  # effectively "not a starter"
    starter_min_good_pitches: int = 3
    starter_pitch_gate_penalty: float = 250_000.0

    # Reliever-only modifier
    reliever_mult: float = 1.05

    vs_rhb_weight: float = 0.70
    vs_lhb_weight: float = 0.30


def add_pitcher_role_scores(
    df: pd.DataFrame,
    weights: PitcherRoleWeights = PitcherRoleWeights(),
) -> pd.DataFrame:
    """Add starter/reliever role scores (overall + vs LHB/RHB)."""

    required = [
        "stuff_vs_lhb", "movement_vs_lhb", "control_vs_lhb", "pbabip_vs_lhb", "hr_rate_vs_lhb",
        "stuff_vs_rhb", "movement_vs_rhb", "control_vs_rhb", "pbabip_vs_rhb", "hr_rate_vs_rhb",
        "stamina",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"add_pitcher_role_scores() missing required columns: {missing}")

    scored = df.copy()

    # Ensure numeric
    for c in required:
        scored[c] = pd.to_numeric(scored[c], errors="coerce").fillna(0)

    pitch_cols = [
        "pitch_fb", "pitch_ch", "pitch_cb", "pitch_sl", "pitch_si", "pitch_sp",
        "pitch_ct", "pitch_fo", "pitch_cc", "pitch_sc", "pitch_kc", "pitch_kn",
    ]
    pitch_cols = [c for c in pitch_cols if c in scored.columns]
    for c in pitch_cols:
        scored[c] = pd.to_numeric(scored[c], errors="coerce").fillna(0)

    # Base vs LHB/RHB
    base_vs_lhb = (
        scored["stuff_vs_lhb"] * weights.stuff
        + scored["movement_vs_lhb"] * weights.movement
        + scored["control_vs_lhb"] * weights.control
        + scored["pbabip_vs_lhb"] * weights.pbabip
        + scored["hr_rate_vs_lhb"] * weights.hr_rate
    )
    base_vs_rhb = (
        scored["stuff_vs_rhb"] * weights.stuff
        + scored["movement_vs_rhb"] * weights.movement
        + scored["control_vs_rhb"] * weights.control
        + scored["pbabip_vs_rhb"] * weights.pbabip
        + scored["hr_rate_vs_rhb"] * weights.hr_rate
    )

    # Starter bonuses
    stamina_bonus = scored["stamina"] * weights.stamina

    if pitch_cols:
        good_pitch_count = scored[pitch_cols].ge(weights.pitch_threshold).sum(axis=1)
    else:
        # fallback if you ever export without per-pitch ratings
        if "pitches" in scored.columns:
            good_pitch_count = pd.to_numeric(scored["pitches"], errors="coerce").fillna(0)
        else:
            good_pitch_count = 0

    scored["starter_pitch_count_good"] = good_pitch_count
    pitch_count_bonus = scored["starter_pitch_count_good"] * weights.pitch_count

    scored["starter_score_vs_lhb"] = base_vs_lhb + stamina_bonus + pitch_count_bonus
    scored["starter_score_vs_rhb"] = base_vs_rhb + stamina_bonus + pitch_count_bonus
    scored["starter_score_overall"] = (
    scored["starter_score_vs_rhb"] * weights.vs_rhb_weight
    + scored["starter_score_vs_lhb"] * weights.vs_lhb_weight
    )
    # --- Starter gating rules ---
    low_stam = scored["stamina"] < weights.starter_min_stamina
    low_pitch = scored["starter_pitch_count_good"] < weights.starter_min_good_pitches

    # If stamina is too low, effectively disqualify as a starter
    scored.loc[low_stam, "starter_score_vs_lhb"] -= weights.starter_stamina_gate_penalty
    scored.loc[low_stam, "starter_score_vs_rhb"] -= weights.starter_stamina_gate_penalty

    # If stamina is OK but pitch depth is too low, penalize starter suitability
    scored.loc[~low_stam & low_pitch, "starter_score_vs_lhb"] -= weights.starter_pitch_gate_penalty
    scored.loc[~low_stam & low_pitch, "starter_score_vs_rhb"] -= weights.starter_pitch_gate_penalty

    # Recompute overall after penalties
    scored["starter_score_overall"] = (scored["starter_score_vs_lhb"] + scored["starter_score_vs_rhb"]) / 2

    # Reliever scores
    scored["reliever_score_vs_lhb"] = base_vs_lhb * weights.reliever_mult
    scored["reliever_score_vs_rhb"] = base_vs_rhb * weights.reliever_mult
    scored["reliever_score_overall"] = (
    scored["reliever_score_vs_rhb"] * weights.vs_rhb_weight
    + scored["reliever_score_vs_lhb"] * weights.vs_lhb_weight
    )
    return scored

@dataclass(frozen=True)
class HitterRoleWeights:
    # Pure hitting weights
    contact: float = 1.00
    power: float = 1.20
    eye: float = 0.85
    gap_power: float = 0.55
    babip: float = 0.35
    avoid_k: float = 0.40

    # Defense component weights (generic)
    fld_pos: float = 1.00  # the position rating itself (fld_SS, fld_CF, etc.)

    # Catcher component weights
    c_framing: float = 1.20
    c_blocking: float = 0.90
    c_arm: float = 0.70

    # Infield component weights
    if_range: float = 1.10
    if_error: float = 0.60
    if_arm: float = 0.70
    turn_dp: float = 0.60

    # Outfield component weights
    of_range: float = 1.10
    of_error: float = 0.55
    of_arm: float = 0.65

    # Eligibility threshold: if fld_POS < this, treat as unplayable
    min_pos_rating: float = 1.0

    # Global multiplier applied to all defense contributions (lower = offense matters more)
    defense_scale: float = 0.70

    # Overall weighting: you face more RHP than LHP
    vs_rhp_weight: float = 0.70
    vs_lhp_weight: float = 0.30

    # Position-specific offense/defense blend (offense_weight, defense_weight)
    # Narrower spread + less defense impact than the first draft.
    pos_blend: dict[str, tuple[float, float]] = field(
        default_factory=lambda: {
            "C": (0.90, 1.10),
            "SS": (0.92, 1.05),
            "CF": (0.93, 1.03),
            "2B": (0.94, 1.00),
            "3B": (0.95, 0.98),
            "RF": (0.96, 0.95),
            "LF": (0.97, 0.92),
            "1B": (0.98, 0.80),
        }
    )


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    """Return numeric series (coerce + fill 0)."""
    return pd.to_numeric(df[col], errors="coerce").fillna(0)


def add_hitter_and_position_scores(
    df: pd.DataFrame,
    weights: HitterRoleWeights = HitterRoleWeights(),
) -> pd.DataFrame:
    """Add hitter scores (overall/vsL/vsR) plus position scores.

    Requires normalized hitter columns from pt_hitters ingest:
      contact, power, eye, gap_power, babip, avoid_k
      contact_vs_lhp, power_vs_lhp, eye_vs_lhp, gap_vs_lhp, babip_vs_lhp, avoid_k_vs_lhp
      contact_vs_rhp, power_vs_rhp, eye_vs_rhp, gap_vs_rhp, babip_vs_rhp, avoid_k_vs_rhp

    Defense inputs:
      fld_C, fld_1B, fld_2B, fld_3B, fld_SS, fld_LF, fld_CF, fld_RF
      c_framing, c_blocking, c_arm
      if_range, if_error, if_arm, turn_dp
      of_range, of_error, of_arm

    Output columns added:
      hitter_score_vs_lhp, hitter_score_vs_rhp, hitter_score_overall
      score_C_overall, score_C_vs_lhp, score_C_vs_rhp
      ... for each position
    """
    required = [
        "name",
        "contact", "power", "eye", "gap_power", "babip", "avoid_k",
        "contact_vs_lhp", "power_vs_lhp", "eye_vs_lhp", "gap_vs_lhp", "babip_vs_lhp", "avoid_k_vs_lhp",
        "contact_vs_rhp", "power_vs_rhp", "eye_vs_rhp", "gap_vs_rhp", "babip_vs_rhp", "avoid_k_vs_rhp",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"add_hitter_and_position_scores() missing required columns: {missing}")

    scored = df.copy()

    # --- Pure hitting scores ---
    # Coerce numeric
    for c in required:
        if c != "name":
            scored[c] = _num(scored, c)

    def hitter_score(prefix: str) -> pd.Series:
        # prefix is "" for overall, "_vs_lhp", "_vs_rhp"
        c = "contact" + prefix
        p = "power" + prefix
        e = "eye" + prefix
        g = ("gap_power" if prefix == "" else "gap" + prefix)
        b = ("babip" if prefix == "" else "babip" + prefix)
        k = ("avoid_k" if prefix == "" else "avoid_k" + prefix)

        return (
            scored[c] * weights.contact
            + scored[p] * weights.power
            + scored[e] * weights.eye
            + scored[g] * weights.gap_power
            + scored[b] * weights.babip
            + scored[k] * weights.avoid_k
        )

    scored["hitter_score_vs_lhp"] = hitter_score("_vs_lhp")
    scored["hitter_score_vs_rhp"] = hitter_score("_vs_rhp")
    scored["hitter_score_overall"] = (
    scored["hitter_score_vs_rhp"] * weights.vs_rhp_weight
    + scored["hitter_score_vs_lhp"] * weights.vs_lhp_weight
    )

    # --- Defense helper scores ---
    # Ensure defense fields exist (if missing, treat as 0)
    for col in [
        "c_framing", "c_blocking", "c_arm",
        "if_range", "if_error", "if_arm", "turn_dp",
        "of_range", "of_error", "of_arm",
        "fld_C", "fld_1B", "fld_2B", "fld_3B", "fld_SS", "fld_LF", "fld_CF", "fld_RF",
    ]:
        if col in scored.columns:
            scored[col] = _num(scored, col)
        else:
            scored[col] = 0

    def defense_score_for_pos(pos: str) -> pd.Series:
        fld = scored[f"fld_{pos}"] * weights.fld_pos

        if pos == "C":
            comp = (
                scored["c_framing"] * weights.c_framing
                + scored["c_blocking"] * weights.c_blocking
                + scored["c_arm"] * weights.c_arm
            )
        elif pos in {"1B", "2B", "3B", "SS"}:
            comp = (
                scored["if_range"] * weights.if_range
                + scored["if_error"] * weights.if_error
                + scored["if_arm"] * weights.if_arm
                + scored["turn_dp"] * weights.turn_dp
            )
        else:  # LF/CF/RF
            comp = (
                scored["of_range"] * weights.of_range
                + scored["of_error"] * weights.of_error
                + scored["of_arm"] * weights.of_arm
            )
        return fld + comp

    # --- Position scores (overall + splits) ---
    positions = ["C", "1B", "2B", "3B", "SS", "LF", "CF", "RF"]

    for pos in positions:
        off_w, def_w = weights.pos_blend[pos]

        def_score = defense_score_for_pos(pos)
        pos_ok = scored[f"fld_{pos}"] >= weights.min_pos_rating
        def_term = weights.defense_scale * def_score

        scored[f"score_{pos}_vs_lhp"] = off_w * scored["hitter_score_vs_lhp"] + def_w * def_term
        scored[f"score_{pos}_vs_rhp"] = off_w * scored["hitter_score_vs_rhp"] + def_w * def_term
        scored[f"score_{pos}_overall"] = (
            scored[f"score_{pos}_vs_rhp"] * weights.vs_rhp_weight
            + scored[f"score_{pos}_vs_lhp"] * weights.vs_lhp_weight
        )

        # Ineligibility gating: if they can’t play the position, bury the score
        scored.loc[~pos_ok, f"score_{pos}_vs_lhp"] = -1_000_000_000.0
        scored.loc[~pos_ok, f"score_{pos}_vs_rhp"] = -1_000_000_000.0
        scored.loc[~pos_ok, f"score_{pos}_overall"] = -1_000_000_000.0

    return scored