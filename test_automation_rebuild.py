from __future__ import annotations

from copy import deepcopy

from ootp_opt.automation.rebuild import build_rebuild_delta
from ootp_opt.automation.ui_plan import build_ui_plan


def card(cid: str, name: str, *, player_type: str = "hitter") -> dict:
    return {
        "candidate_id": f"ootp-pt:card:{cid}:standard",
        "cid": cid,
        "name": name,
        "player_type": player_type,
        "variant": False,
        "owned_cid_copy_count": 1,
    }


def starter(order: int, position: str, selected: dict, backup: dict) -> dict:
    return {
        "batting_order": order,
        "position": position,
        "card": selected,
        "depth": [
            {
                "order": 1,
                "condition": "If Starter tired",
                "card": backup,
            }
        ],
    }


def manifest() -> dict:
    hitter_a = card("101", "Hitter A")
    hitter_b = card("102", "Hitter B")
    bench = card("103", "Bench")
    pitcher_a = card("201", "Pitcher A", player_type="pitcher")
    pitcher_b = card("202", "Pitcher B", player_type="pitcher")
    lineup = [
        starter(1, "SS", hitter_a, bench),
        starter(2, "CF", hitter_b, bench),
    ]
    return {
        "manifest_id": "old-manifest",
        "roster": {
            "expected_total": 5,
            "expected_hitters": 3,
            "expected_pitchers": 2,
            "membership": [hitter_a, hitter_b, bench, pitcher_a, pitcher_b],
        },
        "pitching": {
            "rotation": [{"order": 1, "card": pitcher_a}],
            "bullpen": [
                {
                    "card": pitcher_b,
                    "primary_role": "Middle Relief",
                    "usage": "Normal Usage",
                    "secondary_role": None,
                }
            ],
        },
        "lineups": {
            "vs_rhp": {"starters": deepcopy(lineup)},
            "vs_lhp": {"starters": deepcopy(lineup)},
        },
        "bench_actions": {
            split: {
                "pinch_hitters": [{"order": 1, "card": bench}],
                "pinch_runners": [{"order": 1, "card": bench}],
            }
            for split in ("vs_rhp", "vs_lhp")
        },
    }


def test_rebuild_delta_separates_membership_and_targeted_assignments() -> None:
    previous = manifest()
    current = deepcopy(previous)
    replacement = card("104", "Replacement")
    current["manifest_id"] = "new-manifest"
    current["roster"]["membership"][1] = replacement
    current["lineups"]["vs_rhp"]["starters"][1]["card"] = replacement
    current["lineups"]["vs_lhp"]["starters"][1]["card"] = replacement

    delta = build_rebuild_delta(previous, current)

    assert [entry["cid"] for entry in delta["membership"]["remove"]] == ["102"]
    assert [entry["cid"] for entry in delta["membership"]["add"]] == ["104"]
    assert len(delta["membership"]["retain"]) == 4
    assert delta["lineups"]["vs_rhp"]["batting_order_changed"] is False
    assert delta["lineups"]["vs_rhp"]["batting_order"] == []
    assert [
        entry["position"] for entry in delta["lineups"]["vs_rhp"]["starters"]
    ] == ["CF"]

    current["rebuild"] = delta
    sync = build_ui_plan(current, "sync")
    lineup = build_ui_plan(current, "vs_rhp")
    assert sync["mode"] == "rebuild"
    assert sync["remove"][0][1:5] == ["102", "Hitter B", "hitter", False]
    assert sync["add"][0][1:5] == ["104", "Replacement", "hitter", False]
    assert lineup["starter_strategy"] == "replace_changed_position_slots"
    assert lineup["starter_sequence"] == [[2, "CF", "104", "Replacement"]]
    assert lineup["depth"] == []
    assert lineup["batting_order_strategy"] == "preserve_existing_order"
    assert lineup["batting_order"] == []
    assert "clear_lineup_starters_only" not in lineup["execution"]["required_sequence"]


def test_rebuild_delta_detects_positional_batting_order_change() -> None:
    previous = manifest()
    current = deepcopy(previous)
    current["lineups"]["vs_rhp"]["starters"][0]["position"] = "CF"
    current["lineups"]["vs_rhp"]["starters"][1]["position"] = "SS"
    current["lineups"]["vs_rhp"]["starters"][0]["depth"][0]["condition"] = (
        "If Starter tired or game decided"
    )

    delta = build_rebuild_delta(previous, current)
    current["rebuild"] = delta
    lineup = build_ui_plan(current, "vs_rhp")

    assert delta["lineups"]["vs_rhp"]["batting_order_changed"] is True
    assert len(delta["lineups"]["vs_rhp"]["starters"]) == 2
    assert len(delta["lineups"]["vs_rhp"]["batting_order"]) == 2
    assert lineup["starter_strategy"] == "replace_changed_position_slots"
    assert lineup["batting_order_strategy"] == "reorder_after_depth_chart_updates"
    assert lineup["batting_order"] == [
        [1, "101", "Hitter A"],
        [2, "102", "Hitter B"],
    ]
    sequence = lineup["execution"]["required_sequence"]
    assert "clear_lineup_starters_only" not in sequence
    assert sequence.index("assign_depth_by_direct_drag") < sequence.index(
        "reorder_batting_order_after_depth_chart"
    )


def test_rebuild_delta_limits_pitching_work_to_changed_targets() -> None:
    previous = manifest()
    current = deepcopy(previous)
    current["pitching"]["bullpen"][0]["usage"] = "Use more often"

    delta = build_rebuild_delta(previous, current)
    current["rebuild"] = delta
    plan = build_ui_plan(current, "pitching")

    assert plan["mode"] == "rebuild"
    assert plan["rotation"] == []
    assert plan["bullpen"] == [
        ["202", "Pitcher B", "Middle Relief", "Use more often", None]
    ]
    assert plan["unchanged"] == {"rotation": 1, "bullpen": 0}
