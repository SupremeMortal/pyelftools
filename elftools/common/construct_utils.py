#-------------------------------------------------------------------------------
# elftools: common/construct_utils.py
#
# Some complementary construct utilities
#
# Eli Bendersky (eliben@gmail.com)
# This code is in the public domain
#-------------------------------------------------------------------------------
import itertools

from construct import (
    Subconstruct, Adapter, Bytes, RepeatUntil, SizeofError,
    Construct, ListContainer, Container, StopFieldError,
    singleton, GreedyBytes, NullTerminated, Struct
)


class RepeatUntilExcluding(Subconstruct):
    """ A version of construct's RepeatUntil that doesn't include the last
        element (which caused the repeat to exit) in the return value.

        Only parsing is currently implemented.

        P.S. removed some code duplication
    """
    def __init__(self, predicate, subcon):
        super().__init__(subcon)
        self.predicate = predicate

    def _parse(self, stream, context, path):
        predicate = self.predicate
        if not callable(predicate):
            predicate = lambda _1,_2,_3: predicate
        obj = ListContainer()
        for i in itertools.count():
            context._index = i
            e = self.subcon._parsereport(stream, context, path)
            obj.append(e)
            if predicate(e, obj, context):
                del obj[-1]
                return obj

    def _build(self, obj, stream, context, path):
        raise NotImplementedError('no building')

    def _sizeof(self, context, path):
        raise SizeofError("cannot calculate size, amount depends on actual data", path=path)


def _LEB128_reader():
    """ Read LEB128 variable-length data from the stream. The data is terminated
        by a byte with 0 in its highest bit.
    """
    return RepeatUntil(
        lambda obj, list, ctx: ord(obj) < 0x80,
        Bytes(1)
    )


class _ULEB128Adapter(Adapter):
    """ An adapter for ULEB128, given a sequence of bytes in a sub-construct.
    """
    def _decode(self, obj, context, path):
        value = 0
        for b in reversed(obj):
            value = (value << 7) + (ord(b) & 0x7F)
        return value


class _SLEB128Adapter(Adapter):
    """ An adapter for SLEB128, given a sequence of bytes in a sub-construct.
    """
    def _decode(self, obj, context, path):
        value = 0
        for b in reversed(obj):
            value = (value << 7) + (ord(b) & 0x7F)
        if ord(obj[-1]) & 0x40:
            # negative -> sign extend
            value |= - (1 << (7 * len(obj)))
        return value


@singleton
def ULEB128():
    """ A construct creator for ULEB128 encoding.
    """
    return _ULEB128Adapter(_LEB128_reader())


@singleton
def SLEB128():
    """ A construct creator for SLEB128 encoding.
    """
    return _SLEB128Adapter(_LEB128_reader())


class StreamOffset(Construct):
    """
    Captures the current stream offset

    Parameters:
    * name - the name of the value

    Example:
    StreamOffset("item_offset")
    """
    __slots__ = []
    def __init__(self):
        Construct.__init__(self)
    def _parse(self, stream, context, path):
        return stream.tell()
    def _build(self, obj, stream, context, path):
        context[self.name] = stream.tell()
    def _sizeof(self, context, path):
        return 0


class EmbeddableStruct(Struct):
    r"""
    A special Struct that allows embedding of fields with type Embed.
    """

    def __init__(self, *subcons, **subconskw):
        super().__init__(*subcons, **subconskw)

    def _parse(self, stream, context, path):
        obj = Container()
        obj._io = stream
        context = Container(_ = context, _params = context._params, _root = None, _parsing = context._parsing, _building = context._building, _sizing = context._sizing, _subcons = self._subcons, _io = stream, _index = context.get("_index", None), _parent = obj)
        context._root = context._.get("_root", context)
        for sc in self.subcons:
            try:
                subobj = sc._parsereport(stream, context, path)
                if sc.name:
                    obj[sc.name] = subobj
                    context[sc.name] = subobj
                elif subobj and isinstance(sc, Embed):
                    obj.update(subobj)

            except StopFieldError:
                break
        return obj


class Embed(Subconstruct):
    r"""
    Special wrapper that allows outer multiple-subcons construct to merge fields from another multiple-subcons construct.
    Parsing building and sizeof are deferred to subcon.
    :param subcon: Construct instance, its fields to embed inside a struct or sequence
    Example::
        >>> outer = EmbeddableStruct(
        ...     Embed(Struct(
        ...         "data" / Bytes(4),
        ...     )),
        ... )
        >>> outer.parse(b"1234")
        Container(data=b'1234')
    """

    def __init__(self, subcon):
        super().__init__(subcon)


@singleton
def CStringBytes():
    """
    A stripped back version of CString that returns bytes instead of a unicode string.
    """
    return NullTerminated(GreedyBytes)
