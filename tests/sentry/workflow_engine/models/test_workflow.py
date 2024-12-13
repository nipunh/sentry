from sentry.tasks.post_process import PostProcessJob
from tests.sentry.workflow_engine.test_base import BaseWorkflowTest


class WorkflowTest(BaseWorkflowTest):
    def setUp(self):
        self.workflow, self.detector, self.detector_workflow, self.data_condition_group = (
            self.create_detector_and_workflow()
        )
        self.data_condition = self.data_condition_group.conditions.first()
        self.group, self.event, self.group_event = self.create_group_event()
        self.job = PostProcessJob({"event": self.group_event})

    def test_evaluate_trigger_conditions__condition_new_event__True(self):
        evaluation = self.workflow.evaluate_trigger_conditions(self.job)
        assert evaluation is True

    def test_evaluate_trigger_conditions__condition_new_event__False(self):
        # Update event to have been seen before
        self.group_event.group.times_seen = 5

        evaluation = self.workflow.evaluate_trigger_conditions(self.job)
        assert evaluation is False

    def test_evaluate_trigger_conditions__no_conditions(self):
        self.workflow.when_condition_group = None
        self.workflow.save()

        evaluation = self.workflow.evaluate_trigger_conditions(self.job)
        assert evaluation is True
