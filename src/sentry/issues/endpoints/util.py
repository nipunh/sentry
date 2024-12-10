from collections.abc import Sequence
from datetime import datetime, timedelta

from django.utils import timezone
from rest_framework.exceptions import ParseError
from rest_framework.request import Request

from sentry.api.exceptions import ResourceDoesNotExist
from sentry.api.helpers.environments import get_environments
from sentry.api.helpers.events import get_query_builder_for_group
from sentry.exceptions import InvalidSearchQuery
from sentry.models.environment import Environment
from sentry.models.group import Group
from sentry.search.events.types import ParamsType
from sentry.search.utils import parse_query


def get_event_ids_from_filters(
    referrer: str,
    request: Request,
    group: Group,
    query: str | None,
    start: datetime | None,
    end: datetime | None,
) -> list[str] | None:
    """
    Returns a list of Event IDs matching the environment/query filters.
    If neither are provided it will return `None`, skipping the filter by `EventAttachment.event_id` matches.
    If at least one is provided, but nothing is matched, it will return `[]`, which will result in no attachment matches (as expected).
    """
    default_end = timezone.now()
    default_start = default_end - timedelta(days=90)
    try:
        environments = get_environments(request, group.project.organization)
    except ResourceDoesNotExist:
        environments = []

    # Exit early if no query or environment is specified
    if not query and not environments:
        return None

    params: ParamsType = {
        "project_id": [group.project_id],
        "organization_id": group.project.organization_id,
        "start": start if start else default_start,
        "end": end if end else default_end,
    }

    if environments:
        params["environment"] = [env.name for env in environments]

    # TODO(Leander): This will need to be adapted to paginate with the endpoint somehow, since it'll only get a max of 10k event IDs.
    try:
        snuba_query = get_query_builder_for_group(
            query=query,
            snuba_params=params,
            group=group,
            limit=10000,
            offset=0,
        )
    except InvalidSearchQuery as e:
        raise ParseError(detail=str(e))
    results = snuba_query.run_query(referrer=referrer)
    return [evt["id"] for evt in results["data"]]


def get_event_query(
    request: Request, group: Group, environments: Sequence[Environment]
) -> str | None:
    raw_query = request.GET.get("query")

    if raw_query:
        query_kwargs = parse_query([group.project], raw_query, request.user, environments)
        query = query_kwargs.pop("query", None)
    else:
        query = None

    return query
