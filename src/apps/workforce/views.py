from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import APIView

from apps.identity.permissions import require_store_access
from core.pagination import StandardPagination
from core.shortcuts import object_id_or_404

from .filters import parse_window
from .models import Shift
from .serializers import ShiftSerializer
from .services import create_shift, delete_shift, schedule, update_shift


def _page_number(request) -> int:
    raw = request.query_params.get("page", 1)
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise NotFound("Invalid page.") from None


def _page_link(request, number: int) -> str:
    return replace_query_param(request.build_absolute_uri(), "page", number)


class ShiftList(APIView):
    """The schedule read and shift creation.

    The list *is* the schedule: it carries the window filters, the default week,
    the ordering, and the cache. There is no separate route.
    """

    def get(self, request):
        store_id, start, end = parse_window(request.query_params)
        paginator = StandardPagination()
        page_size = paginator.get_page_size(request) or paginator.page_size
        page = _page_number(request)

        body = schedule(request.user, store_id, (start, end), page, page_size)
        count = body["count"]
        pages = max(1, -(-count // page_size))
        if page < 1 or page > pages:
            raise NotFound("Invalid page.")

        return Response(
            {
                "count": count,
                "next": _page_link(request, page + 1) if page < pages else None,
                "previous": _page_link(request, page - 1) if page > 1 else None,
                "results": body["results"],
            }
        )

    def post(self, request):
        shift = create_shift(request.user, request.data)
        return Response(ShiftSerializer(shift).data, status=status.HTTP_201_CREATED)


class ShiftDetail(APIView):
    def get_object(self) -> Shift:
        shift = object_id_or_404(Shift, self.kwargs["pk"])
        require_store_access(self.request.user, shift.store_id)
        return shift

    def get(self, request, *args, **kwargs):
        return Response(ShiftSerializer(self.get_object()).data)

    def patch(self, request, *args, **kwargs):
        shift = update_shift(request.user, self.get_object(), request.data)
        return Response(ShiftSerializer(shift).data)

    def delete(self, request, *args, **kwargs):
        delete_shift(request.user, self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)
