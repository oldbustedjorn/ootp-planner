from ootp_opt.services.build_timing import BuildTimer, format_duration


def test_build_timer_records_ordered_checkpoints_and_total():
    values = iter([10.0, 11.25, 13.0])
    timer = BuildTimer(clock=lambda: next(values))

    timer.checkpoint("Scoring")
    timing = timer.snapshot()

    assert [(stage.name, stage.seconds) for stage in timing.stages] == [
        ("Scoring", 1.25)
    ]
    assert timing.total_seconds == 3.0
    assert timing.summary_rows() == [
        ("Scoring", "1.250 s"),
        ("Total build time", "3.000 s"),
    ]


def test_format_duration_keeps_small_stages_readable():
    assert format_duration(0.0004) == "<0.001 s"
