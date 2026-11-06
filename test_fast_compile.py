from __future__ import annotations

import pytest

from ootp_opt.automation import fast_compile


def test_compile_rotation_moves_in_manifest_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fast_compile,
        "build_ui_plan",
        lambda _manifest, _section: {
            "rotation": [
                [1, "87374", "Gene Krapp"],
                [2, "86361", "Bruce Hurst"],
            ]
        },
    )

    moves = fast_compile.compile_assignment_moves(
        {},
        "pitching",
        "rotation",
        sources={"87374": (150, 467), "86361": (150, 415)},
        targets={"1": (155, 800), "2": (155, 827)},
    )

    assert moves == [
        {
            "cid": "87374",
            "name": "Gene Krapp",
            "target": "1",
            "from": [150, 467],
            "to": [155, 800],
        },
        {
            "cid": "86361",
            "name": "Bruce Hurst",
            "target": "2",
            "from": [150, 415],
            "to": [155, 827],
        },
    ]


@pytest.mark.parametrize(
    ("family", "plan_key", "entry", "target"),
    [
        ("starters", "starter_sequence", [2, "CF", "100", "Center"], "CF"),
        ("depth", "depth", ["SS", 1, "101", "Backup", "If tired"], "SS:1"),
        ("pinch_hitters", "pinch_hitters", [1, "102", "Hitter"], "1"),
        ("pinch_runners", "pinch_runners", [2, "103", "Runner"], "2"),
    ],
)
def test_compile_lineup_families(
    monkeypatch: pytest.MonkeyPatch,
    family: str,
    plan_key: str,
    entry: list,
    target: str,
) -> None:
    monkeypatch.setattr(
        fast_compile,
        "build_ui_plan",
        lambda _manifest, _section: {plan_key: [entry]},
    )
    cid = str(entry[2] if family in {"starters", "depth"} else entry[1])

    moves = fast_compile.compile_assignment_moves(
        {},
        "vs_rhp",
        family,
        sources={cid: (100, 200)},
        targets={target: (600, 300)},
    )

    assert moves[0]["cid"] == cid
    assert moves[0]["target"] == target


def test_compile_assignment_moves_reports_missing_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fast_compile,
        "build_ui_plan",
        lambda _manifest, _section: {
            "starter_sequence": [[1, "RF", "200", "Right"]]
        },
    )

    with pytest.raises(ValueError, match="Missing source coordinate for CID 200"):
        fast_compile.compile_assignment_moves(
            {}, "vs_lhp", "starters", sources={}, targets={"RF": (1, 1)}
        )


def test_select_assignment_moves_supports_preflight_and_remainder() -> None:
    moves = [{"cid": "1"}, {"cid": "2"}, {"cid": "3"}]

    assert fast_compile.select_assignment_moves(moves, first_only=True) == [moves[0]]
    assert fast_compile.select_assignment_moves(moves, skip_first=1) == moves[1:]

    with pytest.raises(ValueError, match="cannot be combined"):
        fast_compile.select_assignment_moves(
            moves, first_only=True, skip_first=1
        )
