from __future__ import annotations

from typing import Any

import pandas as pd

from ootp_opt.roster.models import HitterRoster, PitcherRoster
from ootp_opt.roster.builder import player_unique_key

POSITION_SCORE_COLUMNS = {
    "C": "score_C_overall",
    "1B": "score_1B_overall",
    "2B": "score_2B_overall",
    "3B": "score_3B_overall",
    "SS": "score_SS_overall",
    "LF": "score_LF_overall",
    "CF": "score_CF_overall",
    "RF": "score_RF_overall",
    "DH": "batting_score_overall",
}


def estimate_purchase_price(row: pd.Series) -> int | None:
    buy = int(row.get("buy_order_high", 0) or 0)
    sell = int(row.get("sell_order_low", 0) or 0)
    last = int(row.get("last_10_price", 0) or 0)

    has_buy = buy > 0
    has_sell = sell > 0
    has_last = last > 0

    # 1. Buy/Sell/Last
    if has_buy and has_sell and has_last:
        return max(buy, last)

    # 2. Buy/Sell
    if has_buy and has_sell:
        return round((buy + sell) / 2)

    # 3. Just Buy
    if has_buy and not has_sell and not has_last:
        return None

    # 4. Buy/Last
    if has_buy and has_last:
        return max(buy, last)

    # 5. Sell/Last
    if has_sell and has_last:
        return min(sell, last)

    # 6. Just Sell
    if has_sell:
        return sell

    # 7. Just Last
    if has_last:
        return last

    return None


def safe_cost_per_gain(
    estimated_price: int | None,
    gain: float,
) -> float | None:
    if estimated_price is None:
        return None

    if gain <= 0:
        return None

    return estimated_price / gain


def find_hitter_upgrades(
    hitter_roster: HitterRoster,
    store_hitters: pd.DataFrame,
    min_gain: float = 0.0,
) -> pd.DataFrame:
    upgrade_rows: list[dict[str, Any]] = []

    candidates = store_hitters.loc[~store_hitters["is_owned"]].copy()
    selected_keys = selected_roster_player_keys_from_hitters(hitter_roster)
    candidates = remove_selected_players(candidates, selected_keys)

    for position, current_player in hitter_roster.starters_by_position.items():
        if position not in POSITION_SCORE_COLUMNS:
            continue

        score_col = POSITION_SCORE_COLUMNS[position]

        if score_col not in candidates.columns:
            continue

        current_score = float(current_player.get(score_col, -1e9))

        eligible = candidates.loc[candidates[score_col] > current_score].copy()

        for _, candidate in eligible.iterrows():
            candidate_score = float(candidate.get(score_col, -1e9))
            gain = candidate_score - current_score

            if gain < min_gain:
                continue

            estimated_price = estimate_purchase_price(candidate)
            cost_per_gain = safe_cost_per_gain(estimated_price, gain)

            upgrade_rows.append(
                {
                    "type": "hitter",
                    "slot": position,
                    "current_player": current_player.get("name", ""),
                    "candidate": candidate.get("name", ""),
                    "candidate_tier": candidate.get("pt_tier", ""),
                    "candidate_value": candidate.get("card_value", 0),
                    **upgrade_card_metadata(candidate),
                    "current_score": round(current_score, 2),
                    "candidate_score": round(candidate_score, 2),
                    "gain": round(gain, 2),
                    "estimated_price": estimated_price,
                    "cost_per_gain": (
                        None if cost_per_gain is None else round(cost_per_gain, 2)
                    ),
                    "sell_order_low": candidate.get("sell_order_low", 0),
                    "buy_order_high": candidate.get("buy_order_high", 0),
                    "last_10_price": candidate.get("last_10_price", 0),
                }
            )

    result = pd.DataFrame(upgrade_rows)

    if result.empty:
        return result

    return result.sort_values(
        ["cost_per_gain", "gain"],
        ascending=[True, False],
        na_position="last",
    ).reset_index(drop=True)


def find_pitcher_upgrades(
    pitcher_roster: PitcherRoster,
    store_pitchers: pd.DataFrame,
    min_gain: float = 0.0,
) -> pd.DataFrame:
    upgrade_rows: list[dict[str, Any]] = []

    candidates = store_pitchers.loc[~store_pitchers["is_owned"]].copy()
    selected_keys = selected_roster_player_keys_from_pitchers(pitcher_roster)
    candidates = remove_selected_players(candidates, selected_keys)

    # Worst SP currently in rotation
    current_sp = pitcher_roster.rotation.sort_values(
        "starter_score_overall", ascending=True
    ).iloc[0]

    current_sp_score = float(current_sp["starter_score_overall"])

    # Worst RP currently in bullpen
    current_rp = pitcher_roster.bullpen.sort_values(
        "reliever_score_overall", ascending=True
    ).iloc[0]

    current_rp_score = float(current_rp["reliever_score_overall"])

    # Current LHP specialist
    current_lhp = pitcher_roster.lefty_specialist.iloc[0]
    current_lhp_score = float(current_lhp["reliever_score_vs_lhb"])

    # SP upgrades
    sp_candidates = candidates.loc[
        candidates["starter_score_overall"] > current_sp_score
    ]

    for _, candidate in sp_candidates.iterrows():
        candidate_score = float(candidate["starter_score_overall"])
        gain = candidate_score - current_sp_score

        if gain < min_gain:
            continue

        estimated_price = estimate_purchase_price(candidate)
        cost_per_gain = safe_cost_per_gain(estimated_price, gain)

        upgrade_rows.append(
            {
                "type": "SP",
                "slot": "SP",
                "current_player": current_sp.get("name", ""),
                "candidate": candidate.get("name", ""),
                "candidate_tier": candidate.get("pt_tier", ""),
                "candidate_value": candidate.get("card_value", 0),
                **upgrade_card_metadata(candidate),
                "current_score": round(current_sp_score, 2),
                "candidate_score": round(candidate_score, 2),
                "gain": round(gain, 2),
                "estimated_price": estimated_price,
                "cost_per_gain": (
                    None if cost_per_gain is None else round(cost_per_gain, 2)
                ),
            }
        )

    # RP upgrades
    rp_candidates = candidates.loc[
        candidates["reliever_score_overall"] > current_rp_score
    ]

    for _, candidate in rp_candidates.iterrows():
        candidate_score = float(candidate["reliever_score_overall"])
        gain = candidate_score - current_rp_score

        if gain < min_gain:
            continue

        estimated_price = estimate_purchase_price(candidate)
        cost_per_gain = safe_cost_per_gain(estimated_price, gain)

        upgrade_rows.append(
            {
                "type": "RP",
                "slot": "Middle Relief",
                "current_player": current_rp.get("name", ""),
                "candidate": candidate.get("name", ""),
                "candidate_tier": candidate.get("pt_tier", ""),
                "candidate_value": candidate.get("card_value", 0),
                **upgrade_card_metadata(candidate),
                "current_score": round(current_rp_score, 2),
                "candidate_score": round(candidate_score, 2),
                "gain": round(gain, 2),
                "estimated_price": estimated_price,
                "cost_per_gain": (
                    None if cost_per_gain is None else round(cost_per_gain, 2)
                ),
            }
        )

    # LHP specialist upgrades
    lhp_candidates = candidates.loc[
        candidates["reliever_score_vs_lhb"] > current_lhp_score
    ]

    for _, candidate in lhp_candidates.iterrows():
        candidate_score = float(candidate["reliever_score_vs_lhb"])
        gain = candidate_score - current_lhp_score

        if gain < min_gain:
            continue

        estimated_price = estimate_purchase_price(candidate)
        cost_per_gain = safe_cost_per_gain(estimated_price, gain)

        upgrade_rows.append(
            {
                "type": "LHP",
                "slot": "LHP Specialist",
                "current_player": current_lhp.get("name", ""),
                "candidate": candidate.get("name", ""),
                "candidate_tier": candidate.get("pt_tier", ""),
                "candidate_value": candidate.get("card_value", 0),
                **upgrade_card_metadata(candidate),
                "current_score": round(current_lhp_score, 2),
                "candidate_score": round(candidate_score, 2),
                "gain": round(gain, 2),
                "estimated_price": estimated_price,
                "cost_per_gain": (
                    None if cost_per_gain is None else round(cost_per_gain, 2)
                ),
            }
        )

    result = pd.DataFrame(upgrade_rows)

    if result.empty:
        return result

    return result.sort_values(
        ["cost_per_gain", "gain"],
        ascending=[True, False],
        na_position="last",
    ).reset_index(drop=True)


def upgrade_card_metadata(candidate: pd.Series) -> dict[str, Any]:
    return {
        "card_title": candidate.get("card_title", ""),
        "is_clubhouse_card": bool(candidate.get("is_clubhouse_card", False)),
    }


def selected_roster_player_keys_from_hitters(hitter_roster: HitterRoster) -> set[str]:
    keys = {player_unique_key(row) for row in hitter_roster.starters_by_position.values()}

    for _, row in hitter_roster.bench_players.iterrows():
        keys.add(player_unique_key(row))

    return keys


def selected_roster_player_keys_from_pitchers(pitcher_roster: PitcherRoster) -> set[str]:
    keys: set[str] = set()

    for roster_part in [
        pitcher_roster.rotation,
        pitcher_roster.bullpen,
        pitcher_roster.lefty_specialist,
        pitcher_roster.long_man,
    ]:
        for _, row in roster_part.iterrows():
            keys.add(player_unique_key(row))

    return keys


def remove_selected_players(
    candidates: pd.DataFrame,
    selected_keys: set[str],
) -> pd.DataFrame:
    if not selected_keys:
        return candidates

    mask = ~candidates.apply(lambda row: player_unique_key(row) in selected_keys, axis=1)
    return candidates.loc[mask].copy()
