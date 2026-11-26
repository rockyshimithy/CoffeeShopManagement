from bson import ObjectId
from bson.errors import InvalidId
from django.http import Http404


def object_id_or_404(model, raw_id):
    """Fetch one row by a 24 character hex id, answering 404 on a bad id."""
    try:
        object_id = ObjectId(raw_id)
    except (InvalidId, TypeError):
        raise Http404 from None
    instance = model.objects.filter(pk=object_id).first()
    if instance is None:
        raise Http404
    return instance
