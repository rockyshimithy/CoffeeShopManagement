import random
import time

from django.db import DatabaseError

ATTEMPTS = 3
BASE_DELAY = 0.005


def retry_on_conflict(operation, attempts=ATTEMPTS, base_delay=BASE_DELAY):
    """Run the operation again when MongoDB aborts it with a write conflict.

    A conflicting write raises ``DatabaseError`` instead of overwriting, so the
    body must be replayed from the start: the aborted attempt left no trace.

    Between attempts the caller waits a random slice proportional to the attempt
    number. Without that pause every loser retries inside the same window and
    collides again, which is measurable: ten simultaneous writes to one document
    reached the database five times out of ten before this delay existed. The
    jitter matters as much as the delay, because identical sleeps keep the
    contenders in step.
    """
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except DatabaseError:
            if attempt == attempts:
                raise
            time.sleep(random.uniform(0, base_delay * 2 ** (attempt - 1)))
