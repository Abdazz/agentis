from app.orchestrator.state import Plan, SubTask, new_plan, mark_subtask_done


def test_plan_round_trips_through_dict():
    plan = Plan(
        goal="Write a report",
        subtasks=[SubTask(id="s1", description="research"), SubTask(id="s2", description="draft")],
    )
    d = plan.model_dump()
    restored = Plan.model_validate(d)
    assert restored.goal == "Write a report"
    assert len(restored.subtasks) == 2
    assert restored.subtasks[0].status == "pending"


def test_new_plan_helper_builds_plan_from_descriptions():
    plan = new_plan("goal", ["a", "b", "c"])
    assert len(plan.subtasks) == 3
    assert plan.subtasks[1].id == "s2"


def test_mark_subtask_done_updates_status_and_result():
    plan = new_plan("goal", ["a", "b"])
    updated = mark_subtask_done(plan, "s1", result="found it")
    assert updated.subtasks[0].status == "done"
    assert updated.subtasks[0].result == "found it"
    assert updated.subtasks[1].status == "pending"
