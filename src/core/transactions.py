from django.db import DatabaseError

ATTEMPTS = 3


def retry_on_conflict(operation, attempts=ATTEMPTS):
    """Run the operation again when MongoDB aborts it with a write conflict.

    A conflicting write raises ``DatabaseError`` instead of overwriting, so the
    body must be replayed from the start: the aborted attempt left no trace.
    """
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except DatabaseError:
            if attempt == attempts:
                raise
