"""Bangladesh divisions, districts and upazilas (static/data/bd-geo.json)."""
import json
from functools import lru_cache

from django.conf import settings

GEO_FILE = settings.BASE_DIR / 'static' / 'data' / 'bd-geo.json'


@lru_cache(maxsize=1)
def geo():
    return json.loads(GEO_FILE.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def upazilas_by_district():
    return {d['name']: set(d['upazilas']) for div in geo()['divisions'] for d in div['districts']}


def is_valid_upazila(district, upazila):
    return upazila in upazilas_by_district().get(district, set())
