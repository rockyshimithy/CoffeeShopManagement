from bson import ObjectId
from bson.errors import InvalidId
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import APIView

from apps.identity.permissions import (
    STORE_DENIED,
    require_stock_access,
)
from core.pagination import StandardPagination
from core.shortcuts import object_id_or_404

from .models import Pool, Stock
from .serializers import StockEventSerializer, StockSerializer
from .services import (
    enrich,
    list_events,
    low_stock,
    pool_is_visible,
    record_count,
    record_movement,
    stock_after,
    stock_scope,
)


def _object_id(value):
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise ValidationError({"detail": "Enter a valid ObjectId."}) from None


def _page_number(request) -> int:
    raw = request.query_params.get("page", 1)
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise NotFound("Invalid page.") from None


def _page_link(request, number: int) -> str:
    return replace_query_param(request.build_absolute_uri(), "page", number)


def _paged_response(request, total: int, page: int, page_size: int, results):
    """One page envelope, shared by the two lists this module paginates itself."""
    pages = max(1, -(-total // page_size))
    if page < 1 or page > pages:
        raise NotFound("Invalid page.")
    return Response(
        {
            "count": total,
            "next": _page_link(request, page + 1) if page < pages else None,
            "previous": _page_link(request, page - 1) if page > 1 else None,
            "results": results,
        }
    )


def _page_args(request):
    paginator = StandardPagination()
    page_size = paginator.get_page_size(request) or paginator.page_size
    return _page_number(request), page_size


class StockList(generics.ListAPIView):
    """The stock list for the actor's scope.

    Ordering is ``product_id``, then pool, then store, which is exactly the unique
    index, so the sort is served by an index and nothing joins.
    """

    serializer_class = StockSerializer
    name = "stock-list"

    def get_queryset(self):
        params = self.request.query_params
        store_id = _object_id(params["store"]) if params.get("store") else None
        queryset = stock_scope(Stock.objects.all(), self.request.user, store_id)

        pool = params.get("pool")
        if pool:
            if pool not in Pool.values:
                raise ValidationError(
                    {"pool": [f"Choose one of: {', '.join(Pool.values)}."]}
                )
            if not pool_is_visible(self.request.user, pool):
                raise PermissionDenied(STORE_DENIED)
            queryset = queryset.filter(pool_type=pool)

        product = params.get("product")
        if product:
            queryset = queryset.filter(product_id=_object_id(product))

        return queryset.order_by("product_id", "pool_type", "store_id")

    def list(self, request, *args, **kwargs):
        rows = self.paginate_queryset(self.get_queryset())
        data = StockSerializer(rows, many=True, context=enrich(rows)).data
        return self.get_paginated_response(data)


class StockLow(APIView):
    """Rows strictly below their product's threshold, worst first."""

    name = "stock-low"

    def get(self, request):
        params = request.query_params
        store_id = _object_id(params["store"]) if params.get("store") else None
        page, page_size = _page_args(request)
        total, rows = low_stock(request.user, store_id, page, page_size)
        data = StockSerializer(rows, many=True, context=enrich(rows)).data
        return _paged_response(request, total, page, page_size, data)


class StockEventList(APIView):
    """One record's history, newest first. No join: the actor name is stored."""

    name = "stock-event-list"

    def get(self, request, pk):
        stock = object_id_or_404(Stock, pk)
        require_stock_access(request.user, stock.store_id)
        page, page_size = _page_args(request)
        total, rows = list_events(stock.pk, page, page_size)
        return _paged_response(
            request, total, page, page_size, StockEventSerializer(rows, many=True).data
        )


class MovementList(APIView):
    """Record a delivery, a sale, or waste. The only route that creates a row."""

    name = "stock-movement-list"

    def post(self, request):
        event = record_movement(request.user, request.data)
        return _recorded(event)


class CountList(APIView):
    """Record an observation of the shelf."""

    name = "stock-count-list"

    def post(self, request):
        event = record_count(request.user, request.data)
        return _recorded(event)


def _recorded(event):
    """The row after the change, so the client needs no second request."""
    stock = stock_after(event)
    return Response(
        {
            "stock": StockSerializer(stock, context=enrich([stock])).data,
            "event": StockEventSerializer(event).data,
        },
        status=status.HTTP_201_CREATED,
    )
