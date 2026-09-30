"""用户源码模板：只锁定明确标记的框架，不解析或重写任意 C。"""
import re

from .fsutil import ServiceError

MARKER = re.compile(r"^[ \t]*/\* EFW USER (BEGIN|END) ([a-z][a-z0-9_]{0,63}) \*/\r?$", re.M)


def fixed_parts(text: str) -> list[str] | None:
    matches = list(MARKER.finditer(text))
    if not matches:
        if 'EFW USER' in text:
            raise ServiceError('TEMPLATE', '模板区域标记不完整，请在外部编辑器中修复。')
        return None
    parts, names, cursor = [], set(), 0
    if len(matches) % 2:
        raise ServiceError('TEMPLATE', '用户逻辑区的 BEGIN/END 必须成对。')
    for begin, end in zip(matches[::2], matches[1::2]):
        name = begin[2]
        start = begin.end() + 1
        finish = end.start() - (2 if text[:end.start()].endswith('\r\n') else 1)
        if begin[1] != 'BEGIN' or end[1] != 'END' or end[2] != name or name in names or finish < start:
            raise ServiceError('TEMPLATE', '模板逻辑区不得嵌套、重名或缺少边界换行。')
        if 'EFW USER' in text[start:finish]:
            raise ServiceError('TEMPLATE', '用户逻辑中不能插入保留的模板标记。')
        names.add(name)
        parts.append(text[cursor:start])
        cursor = finish
    parts.append(text[cursor:])
    return parts


def check_edit(before: str, after: str) -> None:
    fixed = fixed_parts(before)
    updated = fixed_parts(after)
    if fixed is not None and fixed != updated:
        raise ServiceError('TEMPLATE', '模板结构只读：只能修改 EFW USER BEGIN/END 内的用户逻辑。')


def protect_function(source: str, name: str) -> str:
    """仅用于工具自己构造的标准函数；不用于导入用户文件。"""
    first, last = source.index('{') + 1, source.rindex('}')
    body = source[first:last].strip('\n')
    return (source[:first] + f'\n    /* EFW USER BEGIN {name} */\n' + body +
            f'\n    /* EFW USER END {name} */\n' + source[last:])
