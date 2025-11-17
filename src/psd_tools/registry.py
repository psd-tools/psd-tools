"""
Registry pattern utility for creating type registries.

This module provides the ``new_registry`` function which creates a registry
dictionary and a decorator for registering types/handlers. This pattern is
used throughout psd-tools for extensible type systems.

Usage example::

    from psd_tools.registry import new_registry

    # Create a registry and decorator
    TYPES, register = new_registry(attribute='key')

    # Register a handler
    @register('foo')
    class FooHandler:
        pass

    # Look up a handler
    handler = TYPES['foo']()
"""

from typing import Any, Callable, Tuple, TypeVar, Union

T = TypeVar("T")


def new_registry(attribute: Union[str, None] = None) -> Tuple[dict, Callable]:
    """
    Returns an empty dict and a @register decorator.

    The registry dict maps keys to registered functions/classes. The register
    decorator can be used to register functions or classes with specific keys.

    :param attribute: Optional attribute name to set on registered objects.
                     The key will be stored as this attribute on the object.
    :return: Tuple of (registry_dict, register_decorator)

    Example::

        TYPES, register = new_registry(attribute='ostype')

        @register(b'bool')
        def read_bool(fp):
            return struct.unpack('?', fp.read(1))[0]

        # TYPES now contains: {b'bool': read_bool}
        # read_bool.ostype == b'bool'
    """
    registry = {}

    def register(key: Any) -> Callable[[Callable[..., T]], Callable[..., T]]:
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            registry[key] = func
            if attribute:
                setattr(func, attribute, key)
            return func

        return decorator

    return registry, register
