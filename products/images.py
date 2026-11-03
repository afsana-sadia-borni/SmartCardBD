"""Smaller WebP copies of uploaded images, so phones on mobile data download a fraction of the bytes.

For products/phone.jpg we save products/phone.w400.webp, .w800.webp and .w1600.webp next to it
(never wider than the original). Templates ask for one with the `webp` filter, which falls back
to the original image until the copies exist.
"""
import hashlib
import posixpath
from io import BytesIO

from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image, ImageOps

WIDTHS = (400, 800, 1600)
QUALITY = 80
CACHE_SECONDS = 24 * 60 * 60


def variant_name(name, width):
    return f'{posixpath.splitext(name)[0]}.w{width}.webp'


def _cache_key(name):
    return 'webp:' + hashlib.md5(name.encode()).hexdigest()


def make_webp_variants(name, force=False):
    """Create the WebP copies of a stored image. Returns how many files were written."""
    if not name or name.endswith('.webp') or not default_storage.exists(name):
        return 0
    targets = {w: variant_name(name, w) for w in WIDTHS}
    if not force and all(default_storage.exists(n) for n in targets.values()):
        cache.set(_cache_key(name), True, CACHE_SECONDS)
        return 0
    with default_storage.open(name, 'rb') as fh:
        image = ImageOps.exif_transpose(Image.open(fh))
        image.load()
    image = image.convert('RGBA' if image.mode in ('RGBA', 'LA', 'P') else 'RGB')
    written = 0
    for width, target in targets.items():
        copy = image.copy()
        if copy.width > width:
            copy.thumbnail((width, width * 10), Image.LANCZOS)
        out = BytesIO()
        copy.save(out, 'WEBP', quality=QUALITY, method=6)
        if default_storage.exists(target):
            default_storage.delete(target)
        default_storage.save(target, ContentFile(out.getvalue()))
        written += 1
    cache.set(_cache_key(name), True, CACHE_SECONDS)
    return written


def _media_prefix():
    # storage.url('x') minus the 'x' is the URL prefix for stored files, on disk or on S3.
    return default_storage.url('x')[:-1]


def name_from_url(url):
    prefix = _media_prefix()
    return url[len(prefix):] if url and url.startswith(prefix) else None


def has_variants(name):
    found = cache.get(_cache_key(name))
    if found is None:
        found = default_storage.exists(variant_name(name, WIDTHS[0]))
        cache.set(_cache_key(name), found, CACHE_SECONDS if found else 300)
    return found


def webp_url(url, width):
    """URL of the WebP copy of an uploaded image's URL, or the URL itself if there is none."""
    name = name_from_url(str(url or ''))
    if not name or name.endswith('.webp') or not has_variants(name):
        return url
    return default_storage.url(variant_name(name, width))
