from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ParseError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.status import HTTP_404_NOT_FOUND

from sentry import features
from sentry.api.api_owners import ApiOwner
from sentry.api.api_publish_status import ApiPublishStatus
from sentry.api.base import EnvironmentMixin, region_silo_endpoint
from sentry.api.bases.group import GroupEndpoint
from sentry.api.endpoints.group_attachments import get_event_ids_from_filters
from sentry.api.event_search import SearchFilter
from sentry.api.exceptions import ResourceDoesNotExist
from sentry.api.helpers.environments import get_environments
from sentry.api.utils import get_date_range_from_params
from sentry.apidocs.constants import (
    RESPONSE_BAD_REQUEST,
    RESPONSE_FORBIDDEN,
    RESPONSE_NOT_FOUND,
    RESPONSE_UNAUTHORIZED,
)
from sentry.apidocs.examples.replay_examples import ReplayExamples
from sentry.apidocs.parameters import GlobalParams, IssueParams
from sentry.exceptions import InvalidParams, InvalidSearchQuery
from sentry.issues.endpoints.group_events import NoResults
from sentry.issues.endpoints.util import get_event_query
from sentry.models.group import Group
from sentry.replays.endpoints.organization_replay_count import project_in_org_has_sent_replay
from sentry.replays.endpoints.organization_replay_index import ReplayPaginator
from sentry.replays.post_process import process_raw_response
from sentry.replays.usecases.query import Paginators, query_using_optimized_search
from sentry.search.utils import InvalidQuery, parse_query
from sentry.types.ratelimit import RateLimit, RateLimitCategory


@region_silo_endpoint
@extend_schema(tags=["Replays"])
class GroupReplayEndpoint(GroupEndpoint, EnvironmentMixin):
    owner = ApiOwner.ISSUES
    publish_status = {
        "GET": ApiPublishStatus.PRIVATE,
    }

    enforce_rate_limit = True
    rate_limits = {
        "GET": {
            RateLimitCategory.IP: RateLimit(limit=20, window=1),
            RateLimitCategory.USER: RateLimit(limit=20, window=1),
            RateLimitCategory.ORGANIZATION: RateLimit(limit=20, window=1),
        }
    }

    @extend_schema(
        # TODO(Leander): Replace with real value
        # examples=ReplayExamples.GET_REPLAY_COUNTS,
        operation_id="List an Issue's Replays",
        parameters=[
            GlobalParams.ORG_ID_OR_SLUG,
            IssueParams.ISSUES_OR_GROUPS,
            IssueParams.ISSUE_ID,
            GlobalParams.START,
            GlobalParams.END,
            GlobalParams.STATS_PERIOD,
            GlobalParams.ENVIRONMENT,
            OpenApiParameter(
                name="query",
                location=OpenApiParameter.QUERY,
                type=OpenApiTypes.STR,
                description="An optional search query for filtering events.",
                required=False,
            ),
        ],
        responses={
            # TODO(Leander): Replace with real value
            # 200: inline_sentry_response_serializer("ReplayCounts", dict[int, int]),
            400: RESPONSE_BAD_REQUEST,
            401: RESPONSE_UNAUTHORIZED,
            403: RESPONSE_FORBIDDEN,
            404: RESPONSE_NOT_FOUND,
        },
    )
    def get(self, request: Request, group: Group) -> Response:
        """
        Return a list of replays bound to an issue
        """
        organization = group.project.organization
        if not features.has("organizations:session-replay", organization, actor=request.user):
            return Response(status=HTTP_404_NOT_FOUND)

        # TODO(Leander): Uncomment this after finishing testing
        # if not project_in_org_has_sent_replay(organization):
        #     return Response({})

        try:
            start, end = get_date_range_from_params(request.GET, optional=True)
        except InvalidParams as e:
            raise ParseError(detail=str(e))

        try:
            environments = get_environments(request, group.project.organization)
        except ResourceDoesNotExist:
            return Response([])

        try:
            query = get_event_query(request=request, group=group, environments=environments)
        except InvalidQuery as exc:
            return Response({"detail": str(exc)}, status=400)
        except NoResults:
            return Response([])

        event_ids = get_event_ids_from_filters(
            referrer=f"api.group-replays.{group.issue_category.name.lower()}",
            request=request,
            group=group,
            start=start,
            query=query,
            end=end,
        )

        def data_fn(offset: int, limit: int):
            return query_using_optimized_search(
                fields=request.query_params.getlist("field"),
                search_filters=[SearchFilter("error_ids", "=", event_ids)],
                environments=environments,
                sort="finished_at",
                pagination=Paginators(limit, offset),
                organization=organization,
                project_ids=[group.project_id],
                period_start=start,
                period_stop=end,
                request_user_id=request.user.id if request.user else None,
            )

        return self.paginate(
            request=request,
            paginator=ReplayPaginator(data_fn=data_fn),
            on_results=lambda results: {
                "data": process_raw_response(
                    results,
                    fields=request.query_params.getlist("field"),
                )
            },
        )
