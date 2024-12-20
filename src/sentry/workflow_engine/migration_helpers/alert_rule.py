from sentry.deletions.models.scheduleddeletion import RegionScheduledDeletion
from sentry.incidents.grouptype import MetricAlertFire
from sentry.incidents.models.alert_rule import AlertRule
from sentry.incidents.utils.types import DATA_SOURCE_SNUBA_QUERY_SUBSCRIPTION
from sentry.snuba.models import QuerySubscription, SnubaQuery
from sentry.snuba.subscriptions import bulk_delete_snuba_subscriptions
from sentry.users.services.user import RpcUser
from sentry.workflow_engine.models import (
    AlertRuleDetector,
    AlertRuleWorkflow,
    DataConditionGroup,
    DataSource,
    Detector,
    DetectorState,
    DetectorWorkflow,
    Workflow,
    WorkflowDataConditionGroup,
)
from sentry.workflow_engine.types import DetectorPriorityLevel


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
        type="snuba_query_subscription",
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


def get_data_source(alert_rule: AlertRule) -> DataSource | None:
    # TODO: if dual deleting, then we should delete the subscriptions here and not in logic.py
    snuba_query = alert_rule.snuba_query
    organization = alert_rule.organization
    if not snuba_query or not organization:
        # This shouldn't be possible, but just in case.
        return None
    try:
        query_subscription = QuerySubscription.objects.get(snuba_query=snuba_query.id)
    except QuerySubscription.DoesNotExist:
        return None
    try:
        data_source = DataSource.objects.get(
            organization=organization,
            query_id=query_subscription.id,
            type=DATA_SOURCE_SNUBA_QUERY_SUBSCRIPTION,
        )
    except DataSource.DoesNotExist:
        return None
    bulk_delete_snuba_subscriptions([query_subscription])
    return data_source


def dual_delete_migrated_alert_rule(
    alert_rule: AlertRule,
    user: RpcUser | None = None,
) -> None:
    try:
        alert_rule_detector = AlertRuleDetector.objects.get(alert_rule=alert_rule)
        alert_rule_workflow = AlertRuleWorkflow.objects.get(alert_rule=alert_rule)
    except (AlertRuleDetector.DoesNotExist, AlertRuleWorkflow.DoesNotExist):
        # TODO: log failure
        return

    detector: Detector = alert_rule_detector.detector
    data_condition_group: DataConditionGroup | None = detector.workflow_condition_group

    data_source = get_data_source(alert_rule=alert_rule)
    if data_source is None:
        # TODO: log failure
        return

    # deleting the alert_rule would also delete alert_rule_workflow, but let's do it here
    RegionScheduledDeletion.schedule(instance=alert_rule_workflow, days=0, actor=user)
    # also deletes alert_rule_detector, detector_workflow, detector_state
    RegionScheduledDeletion.schedule(instance=detector, days=0, actor=user)
    # also deletes workflow_data_condition_group
    if data_condition_group:
        RegionScheduledDeletion.schedule(instance=data_condition_group, days=0, actor=user)
    RegionScheduledDeletion.schedule(instance=data_source, days=0, actor=user)

    return
