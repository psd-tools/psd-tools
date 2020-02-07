"""
Validation functions for attr.
"""
import attr
from attr.validators import in_

__all__ = ['in_', 'range_']


@attr.s(repr=False, slots=True, hash=True)
class _RangeValidator(object):
    minimum = attr.ib()
    maximum = attr.ib()

    def __call__(self, inst, attr, value):
        try:
            range_options = self.minimum <= value and value <= self.maximum
        except TypeError:
            range_options = False

        if not range_options:
            raise ValueError("'{name}' must be in range []")

    def __repr__(self):
        return "<range_ validator with [{minimum!r}, {maximum!r}]".format(
            minimum=self.minimum, maximum=self.maximum
        )


def range_(minimum, maximum):
    """
    A validator that raises a :exc:`ValueError` if the initializer is called
    with a value that does not belong in the [minimum, maximum] range. The
    check is performed using ``minimum <= value and value <= maximum``
    """
    return _RangeValidator(minimum, maximum)
