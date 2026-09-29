import pandas as pd

from ootp_opt.roster.bullpen_usage import (
    NORMAL_USAGE,
    USE_LESS_OFTEN,
    USE_MORE_OFTEN,
    assign_middle_relief_usage,
)


def bullpen(scores: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "name": [f"Reliever {index}" for index in range(len(scores))],
            "reliever_score_overall": scores,
        }
    )


def test_clear_upper_cluster_is_used_more_often():
    assigned = assign_middle_relief_usage(
        bullpen([465.8, 461.3, 454.2, 422.2, 414.2, 413.1])
    )

    assert assigned["usage_option"].tolist() == [
        USE_MORE_OFTEN,
        USE_MORE_OFTEN,
        USE_MORE_OFTEN,
        NORMAL_USAGE,
        NORMAL_USAGE,
        NORMAL_USAGE,
    ]


def test_equal_scores_all_receive_normal_usage():
    assigned = assign_middle_relief_usage(bullpen([400.0] * 6))

    assert assigned["usage_option"].tolist() == [NORMAL_USAGE] * 6


def test_two_clear_breaks_use_all_three_usage_options():
    assigned = assign_middle_relief_usage(
        bullpen([480.0, 475.0, 440.0, 435.0, 400.0, 395.0])
    )

    assert assigned["usage_option"].tolist() == [
        USE_MORE_OFTEN,
        USE_MORE_OFTEN,
        NORMAL_USAGE,
        NORMAL_USAGE,
        USE_LESS_OFTEN,
        USE_LESS_OFTEN,
    ]


def test_clear_lower_outlier_is_used_less_often():
    assigned = assign_middle_relief_usage(
        bullpen([460.0, 455.0, 450.0, 445.0, 440.0, 400.0])
    )

    assert assigned["usage_option"].tolist() == [
        NORMAL_USAGE,
        NORMAL_USAGE,
        NORMAL_USAGE,
        NORMAL_USAGE,
        NORMAL_USAGE,
        USE_LESS_OFTEN,
    ]


def test_smooth_score_distribution_stays_normal():
    assigned = assign_middle_relief_usage(
        bullpen([460.0, 450.0, 440.0, 430.0, 420.0, 410.0])
    )

    assert assigned["usage_option"].tolist() == [NORMAL_USAGE] * 6
