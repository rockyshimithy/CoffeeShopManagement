"""The schedule cache.

A cached schedule page is a document keyed by the stores in scope, the window,
the page, and the revision of every store in scope. Nothing is invalidated:
every shift write bumps a revision, which renames the key, so a stale page is
unreachable rather than deleted. That is what keeps a read correct with more
than one worker process (FR-022, SC-005).
"""

import hashlib
import json
from datetime import timedelta

from django.utils import timezone

from .models import ScheduleRevision, ScheduleSnapshot

SNAPSHOT_TTL = timedelta(hours=1)


def scope_revisions(store_ids) -> dict:
    """The revision of every store in scope, missing stores counting as zero."""
    return dict(
        ScheduleRevision.objects.filter(store_id__in=store_ids).values_list(
            "store_id", "revision"
        )
    )


def schedule_key(store_ids, window, page: int, page_size: int) -> str:
    revisions = scope_revisions(store_ids)
    payload = {
        "stores": sorted(
            [str(store_id), revisions.get(store_id, 0)] for store_id in store_ids
        ),
        "from": window[0].isoformat(),
        "to": window[1].isoformat(),
        "page": page,
        "page_size": page_size,
    }
    raw = json.dumps(payload, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()


def read_snapshot(key: str) -> dict | None:
    row = ScheduleSnapshot.objects.filter(key=key).first()
    return row.body if row else None


def write_snapshot(key: str, body: dict) -> None:
    """Store one page, dropping anything older than the TTL on the way.

    The cleanup is global rather than per store: a store that has been deleted
    never appears in an actor's scope again, so a per store sweep would never
    visit its stranded rows.
    """
    cutoff = timezone.now() - SNAPSHOT_TTL
    ScheduleSnapshot.objects.filter(created_at__lt=cutoff).delete()
    ScheduleSnapshot.objects.get_or_create(key=key, defaults={"body": body})
