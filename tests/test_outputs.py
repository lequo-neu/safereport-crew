def test_the_pareto_front_keeps_only_points_nothing_beats():
    from safereport.outputs import pareto_chart, pareto_front

    points = [{"label": "a", "cost": 0.0, "accuracy": 0.41}, {"label": "b", "cost": 0.05, "accuracy": 0.61},
              {"label": "c", "cost": 0.08, "accuracy": 0.71}, {"label": "d", "cost": 0.09, "accuracy": 0.5}]  # fmt: skip
    assert [p["label"] for p in pareto_front(points)] == ["a", "b", "c"]
    assert pareto_chart(points).startswith(b"\x89PNG")
