"""Bangla digits (১২৩) for prices and counts when the visitor turns on Bangla numbers."""
from contextvars import ContextVar

use_bn_digits = ContextVar('use_bn_digits', default=False)

BN_DIGITS = str.maketrans('0123456789', '০১২৩৪৫৬৭৮৯')


def to_bn_digits(text):
    return str(text).translate(BN_DIGITS)


def localize_digits(text):
    """Return text with Bangla digits if the current request asked for them."""
    return to_bn_digits(text) if use_bn_digits.get() else str(text)
