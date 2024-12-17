import logging

from sentry.incidents.grouptype import MetricAlertFire
from sentry.incidents.models.alert_rule import (
    AlertRule,
    AlertRuleThresholdType,
    AlertRuleTrigger,
    AlertRuleTriggerAction,
)
from sentry.snuba.models import QuerySubscription, SnubaQuery
from sentry.users.services.user import RpcUser
from sentry.workflow_engine.models import (
    Action,
    AlertRuleDetector,
    AlertRuleTriggerDataCondition,
    AlertRuleWorkflow,
    DataCondition,
    DataConditionGroup,
    DataConditionGroupAction,
    DataSource,
    Detector,
    DetectorState,
    DetectorWorkflow,
    Workflow,
    WorkflowDataConditionGroup,
)
from sentry.workflow_engine.models.data_condition import Condition, ConditionType
from sentry.workflow_engine.types import DataSourceType, DetectorPriorityLevel

logger = logging.getLogger(__name__)


def migrate_metric_action(
    alert_rule_trigger_action: AlertRuleTriggerAction,
) -> tuple[Action, DataConditionGroupAction] | None:
    try:
        alert_rule_trigger_data_condition = AlertRuleTriggerDataCondition.objects.get(
            alert_rule_trigger=alert_rule_trigger_action.alert_rule_trigger
        )
    except AlertRuleTriggerDataCondition.DoesNotExist:
        logger.exception(
            "AlertRuleTriggerDataCondition does not exist",
            extra={"alert_rule_trigger_id": alert_rule_trigger_action.alert_rule_trigger.id},
        )
        return None

    data = {
        "type": alert_rule_trigger_action.type,
        "sentry_app_id": alert_rule_trigger_action.sentry_app_id,
        "sentry_app_config": alert_rule_trigger_action.sentry_app_config,
    }
    action = Action.objects.create(
        required=False,
        type=Action.Type.NOTIFICATION,  # TODO: this is going to change to be the delivery method
        data=data,
        integration_id=alert_rule_trigger_action.integration_id,
        target_display=alert_rule_trigger_action.target_display,
        target_identifier=alert_rule_trigger_action.target_identifier,
        target_type=alert_rule_trigger_action.target_type,
    )
    data_condition_group_action = DataConditionGroupAction.objects.create(
        condition_group_id=alert_rule_trigger_data_condition.data_condition.condition_group.id,
        action_id=action.id,
    )
    return action, data_condition_group_action


def migrate_metric_data_condition(
    alert_rule_trigger: AlertRuleTrigger,
) -> tuple[DataCondition, AlertRuleTriggerDataCondition] | None:
    try:
        alert_rule_detector = AlertRuleDetector.objects.get(
            alert_rule=alert_rule_trigger.alert_rule
        )
    except AlertRuleDetector.DoesNotExist:
        logger.exception(
            "AlertRuleDetector does not exist",
            extra={"alert_rule_id": alert_rule_trigger.alert_rule.id},
        )
        return None

    threshold_to_condition = {
        AlertRuleThresholdType.ABOVE.value: Condition.GREATER,
        AlertRuleThresholdType.BELOW.value: Condition.LESS,
        # TODO add ABOVE_AND_BELOW for anomaly detection
    }

    data_condition_group = alert_rule_detector.detector.workflow_condition_group
    if not data_condition_group:
        logger.warning(
            "Could not find data_condition_group",
            extra={"detector_id": alert_rule_detector.id},
        )
        return None

    condition_result = (
        DetectorPriorityLevel.MEDIUM
        if alert_rule_trigger.label == "warning"
        else DetectorPriorityLevel.HIGH
    )
    threshold_type = alert_rule_trigger.alert_rule.threshold_type
    # XXX: we read the threshold type off of the alert_rule and NOT the alert_rule_trigger
    # alert_rule_trigger.threshold_type is a deprecated feature we are not moving over
    if threshold_type is None:
        logger.warning(
            "No threshold type",
            extra={"alert_rule_id": alert_rule_trigger.alert_rule.id},
        )
        return None

    data_condition = DataCondition.objects.create(
        condition=threshold_to_condition.get(threshold_type, AlertRuleThresholdType.ABOVE.value),
        comparison=alert_rule_trigger.alert_threshold,
        condition_result=condition_result,
        type=ConditionType.METRIC_CONDITION,
        condition_group=data_condition_group,
    )
    alert_rule_trigger_data_condition = AlertRuleTriggerDataCondition.objects.create(
        alert_rule_trigger=alert_rule_trigger, data_condition=data_condition
    )
    return data_condition, alert_rule_trigger_data_condition


def create_metric_alert_lookup_tables(
    alert_rule: AlertRule,
    detector: Detector,
    workflow: Workflow,
    data_source: DataSource,
    data_condition_group: DataConditionGroup,
) -> tuple[AlertRuleDetector, AlertRuleWorkflow, DetectorWorkflow, WorkflowDataConditionGroup]:
    alert_rule_detector = AlertRuleDetector.objects.create(alert_rule=alert_rule, detector=detector)
    alert_rule_workflow = AlertRuleWorkflow.objects.create(alert_rule=alert_rule, workflow=workflow)
    detector_workflow = DetectorWorkflow.objects.create(detector=detector, workflow=workflow)
    workflow_data_condition_group = WorkflowDataConditionGroup.objects.create(
        condition_group=data_condition_group, workflow=workflow
    )
    return (
        alert_rule_detector,
        alert_rule_workflow,
        detector_workflow,
        workflow_data_condition_group,
    )


def create_data_source(
    organization_id: int, snuba_query: SnubaQuery | None = None
) -> DataSource | None:
    if not snuba_query:
        return None

    try:
        query_subscription = QuerySubscription.objects.get(snuba_query=snuba_query.id)
    except QuerySubscription.DoesNotExist:
        return None

    return DataSource.objects.create(
        organization_id=organization_id,
        query_id=query_subscription.id,
        type=DataSourceType.SNUBA_QUERY_SUBSCRIPTION,
    )


def create_data_condition_group(organization_id: int) -> DataConditionGroup:
    return DataConditionGroup.objects.create(
        logic_type=DataConditionGroup.Type.ANY,
        organization_id=organization_id,
    )


def create_workflow(
    name: str,
    organization_id: int,
    data_condition_group: DataConditionGroup,
    user: RpcUser | None = None,
) -> Workflow:
    return Workflow.objects.create(
        name=name,
        organization_id=organization_id,
        when_condition_group=data_condition_group,
        enabled=True,
        created_by_id=user.id if user else None,
    )


def create_detector(
    alert_rule: AlertRule,
    project_id: int,
    data_condition_group: DataConditionGroup,
    user: RpcUser | None = None,
) -> Detector:
    return Detector.objects.create(
        project_id=project_id,
        enabled=True,
        created_by_id=user.id if user else None,
        name=alert_rule.name,
        workflow_condition_group=data_condition_group,
        type=MetricAlertFire.slug,
        description=alert_rule.description,
        owner_user_id=alert_rule.user_id,
        owner_team=alert_rule.team,
        config={  # TODO create a schema
            "threshold_period": alert_rule.threshold_period,
            "sensitivity": alert_rule.sensitivity,
            "seasonality": alert_rule.seasonality,
            "comparison_delta": alert_rule.comparison_delta,
        },
    )


def migrate_alert_rule(
    alert_rule: AlertRule,
    user: RpcUser | None = None,
) -> (
    tuple[
        DataSource,
        DataConditionGroup,
        Workflow,
        Detector,
        DetectorState,
        AlertRuleDetector,
        AlertRuleWorkflow,
        DetectorWorkflow,
        WorkflowDataConditionGroup,
    ]
    | None
):
    organization_id = alert_rule.organization_id
    project = alert_rule.projects.first()
    if not project:
        return None

    data_source = create_data_source(organization_id, alert_rule.snuba_query)
    if not data_source:
        return None

    data_condition_group = create_data_condition_group(organization_id)
    workflow = create_workflow(alert_rule.name, organization_id, data_condition_group, user)
    detector = create_detector(alert_rule, project.id, data_condition_group, user)

    data_source.detectors.set([detector])
    detector_state = DetectorState.objects.create(
        detector=detector,
        active=False,
        state=DetectorPriorityLevel.OK,
    )
    alert_rule_detector, alert_rule_workflow, detector_workflow, workflow_data_condition_group = (
        create_metric_alert_lookup_tables(
            alert_rule, detector, workflow, data_source, data_condition_group
        )
    )
    return (
        data_source,
        data_condition_group,
        workflow,
        detector,
        detector_state,
        alert_rule_detector,
        alert_rule_workflow,
        detector_workflow,
        workflow_data_condition_group,
    )
