"""Document resources a layer references by id, carried across documents."""

import logging
import uuid
from collections.abc import Iterable, Iterator
from copy import deepcopy
from typing import Any

import attrs

from psd_tools.api.protocols import PSDProtocol
from psd_tools.constants import Tag
from psd_tools.psd.base import DictElement, ListElement
from psd_tools.psd.descriptor import String
from psd_tools.psd.layer_and_mask import LayerRecord
from psd_tools.psd.tagged_blocks import TaggedBlocks
from psd_tools.terminology import Enum, Key

logger = logging.getLogger(__name__)

_PATTERN_TAGS = (Tag.PATTERNS1, Tag.PATTERNS2, Tag.PATTERNS3)
_LINKED_TAGS = (
    Tag.LINKED_LAYER1,
    Tag.LINKED_LAYER2,
    Tag.LINKED_LAYER3,
    Tag.LINKED_LAYER_EXTERNAL,
)
_PLACED_TAGS = (Tag.PLACED_LAYER1, Tag.PLACED_LAYER2)
_SMART_OBJECT_TAGS = (Tag.SMART_OBJECT_LAYER_DATA1, Tag.SMART_OBJECT_LAYER_DATA2)


def _descriptors(node: Any) -> Iterator[DictElement]:
    """Every descriptor reachable from *node*."""
    stack = [node]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if isinstance(node, (str, bytes, int, float)) or id(node) in seen:
            continue
        seen.add(id(node))
        if isinstance(node, DictElement):
            yield node
            stack.extend(node._items.values())
        elif isinstance(node, ListElement):
            stack.extend(node._items)
        elif isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, (list, tuple)):
            stack.extend(node)
        elif attrs.has(type(node)):
            stack.extend(getattr(node, f.name) for f in attrs.fields(type(node)))


def _bare(value: Any) -> str | None:
    """The id in a descriptor ``String``, without its trailing NUL."""
    return value.value.rstrip("\x00") if isinstance(value, String) else None


class ResourceTransfer:
    """Carries the patterns and linked smart objects layers use into *dest*.

    Resources are copied, never shared. An id the destination already uses for
    different content is replaced by a fresh one in the layer's descriptors.
    A reference the source cannot resolve is left as it is. One instance
    serves a whole operation, so layers sharing a resource share its transfer.
    """

    def __init__(self, dest: PSDProtocol) -> None:
        self._dest = dest
        self._ids: dict[tuple[int, str, str], str] = {}

    def add(self, source: PSDProtocol, records: Iterable[LayerRecord]) -> None:
        """Carry what *records* reference from *source*, rewriting their ids."""
        for record in records:
            blocks = record.tagged_blocks
            for tag in list(blocks.keys()):
                data = blocks.get_data(tag)
                if data is None or tag in _PLACED_TAGS:
                    continue
                if tag in _SMART_OBJECT_TAGS:
                    self._remap(source, "linked", getattr(data, "data", None))
                for descriptor in _descriptors(data):
                    pattern = descriptor.get(Enum.Pattern)
                    if isinstance(pattern, DictElement):
                        self._remap(source, "pattern", pattern)
            for tag in _PLACED_TAGS:
                placed = blocks.get_data(tag)
                if placed is not None:
                    key = (id(source), "linked", placed.uuid.decode().rstrip("\x00"))
                    placed.uuid = self._ids.get(key, key[2]).encode()

    def _remap(self, source: PSDProtocol, kind: str, holder: Any) -> None:
        if not isinstance(holder, DictElement):
            return
        old = holder.get(Key.ID)
        key = _bare(old)
        if key is None:
            return
        memo = (id(source), kind, key)
        if memo not in self._ids:
            transfer = self._pattern if kind == "pattern" else self._linked
            self._ids[memo] = transfer(source, key)
        new = self._ids[memo]
        if new != key:
            nul = "\x00" if old.value.endswith("\x00") else ""
            holder[Key.ID] = String(new + nul)

    def _blocks(self, create: bool) -> TaggedBlocks | None:
        dest = self._dest
        if dest.tagged_blocks is None and create:
            logger.debug("Creating tagged blocks for psdimage.")
            dest._record.layer_and_mask_information.tagged_blocks = TaggedBlocks()
        return dest.tagged_blocks

    def _target(self, tag: Tag) -> Any:
        """The destination's list for *tag*, created if absent; ``None`` if malformed."""
        blocks = self._blocks(create=True)
        if blocks is None:
            return None
        target = blocks.get_data(tag)
        if target is None:
            if tag in blocks:
                return None
            blocks.set_data(tag, [])
            target = blocks.get_data(tag)
        return target

    def _pattern(self, source: PSDProtocol, pattern_id: str) -> str:
        found = _find(source, _PATTERN_TAGS, "pattern_id", pattern_id)
        if not found:
            return pattern_id
        tag, pattern = found[0]
        present = _find(self._dest, _PATTERN_TAGS, "pattern_id", pattern_id)
        if present and present[0][1] == pattern:
            return pattern_id
        new = str(uuid.uuid4()) if present else pattern_id
        target = self._target(tag)
        if target is not None:
            clone = deepcopy(pattern)
            clone.pattern_id = new
            target.append(clone)
        return new

    def _linked(self, source: PSDProtocol, unique_id: str) -> str:
        found = _find(source, _LINKED_TAGS, "uuid", unique_id)
        if not found:
            return unique_id
        present = _find(self._dest, _LINKED_TAGS, "uuid", unique_id)
        if [item for _, item in present] == [item for _, item in found]:
            return unique_id
        new = str(uuid.uuid4()) if present else unique_id
        for tag, item in found:
            target = self._target(tag)
            if target is not None:
                clone = deepcopy(item)
                clone.uuid = new
                target.append(clone)
        return new


def _find(
    psd: PSDProtocol, tags: tuple[Tag, ...], attribute: str, value: str
) -> list[tuple[Tag, Any]]:
    """Items of *psd*'s *tags* blocks whose *attribute* is *value*."""
    if psd.tagged_blocks is None:
        return []
    return [
        (tag, item)
        for tag in tags
        for item in psd.tagged_blocks.get_data(tag) or ()
        if getattr(item, attribute) == value
    ]
