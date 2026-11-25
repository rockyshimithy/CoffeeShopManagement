from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """The one pager for every list endpoint: 20 by default, 100 at most."""

    page_size_query_param = "page_size"
    max_page_size = 100
