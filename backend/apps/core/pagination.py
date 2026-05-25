from rest_framework.pagination import CursorPagination


class FinancialCursorPagination(CursorPagination):
    """
    Cursor-based pagination for append-only financial lists
    (transactions, payments, advances, disbursements, welfare claims).

    Cursor pagination is safe for live financial data:
      - Never uses OFFSET, so inserts between pages do not shift results.
      - Does not expose total row count (no information leak).
      - The cursor is an opaque, signed token — clients cannot forge positions.

    Response shape:
        {
          "next":     "https://…?cursor=cD0yMDI2…",  # null on last page
          "previous": "https://…?cursor=cD0yMDI2…",  # null on first page
          "results":  [ … ]
        }

    Query params:
        cursor    — opaque token from next/previous links (do not construct manually)
        page_size — number of results per page (default 30, max 100)
    """

    ordering              = '-created_at'   # must match an index on every model using this
    page_size             = 30
    page_size_query_param = 'page_size'     # ?page_size=50 for custom size
    max_page_size         = 100
