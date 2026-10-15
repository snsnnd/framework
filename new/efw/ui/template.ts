// 与 studio_core/source_template.py 相同的标记规则。函数体在 `/* EFW USER BEGIN <name> */`
// 与 `/* EFW USER END <name> */` 之间；其余属于工具维护的固定结构。
const MARKER = /^[ \t]*\/\* EFW USER (BEGIN|END) ([a-z][a-z0-9_]{0,63}) \*\/\r?$/gm;

export interface TemplateSegment { from: number; to: number; editable: boolean }
export interface TemplateInfo {
  ok: boolean;
  fixed: string[] | null;
  segments: TemplateSegment[];
}

export function parseTemplate(text: string): TemplateInfo {
  const matches = [...text.matchAll(MARKER)].map((m) => ({
    kind: m[1] as 'BEGIN' | 'END', name: m[2], start: m.index, end: m.index + m[0].length,
  }));
  if (!matches.length) {
    if (text.includes('EFW USER')) return { ok: false, fixed: null, segments: [] };
    return { ok: true, fixed: null, segments: [{ from: 0, to: text.length, editable: true }] };
  }
  if (matches.length % 2) return { ok: false, fixed: null, segments: [] };
  const fixed: string[] = [];
  const segments: TemplateSegment[] = [];
  const names = new Set<string>();
  let cursor = 0;
  for (let i = 0; i < matches.length; i += 2) {
    const begin = matches[i];
    const end = matches[i + 1];
    if (begin.kind !== 'BEGIN' || end.kind !== 'END' || end.name !== begin.name || names.has(begin.name)) {
      return { ok: false, fixed: null, segments: [] };
    }
    const newline = text[end.start - 1] === '\n' ? (text[end.start - 2] === '\r' ? 2 : 1) : 0;
    const start = begin.end + 1;
    const finish = end.start - newline;
    if (finish < start || text.slice(start, finish).includes('EFW USER')) {
      return { ok: false, fixed: null, segments: [] };
    }
    names.add(begin.name);
    fixed.push(text.slice(cursor, start));
    segments.push({ from: cursor, to: start, editable: false });
    segments.push({ from: start, to: finish, editable: true });
    cursor = finish;
  }
  fixed.push(text.slice(cursor));
  segments.push({ from: cursor, to: text.length, editable: false });
  return { ok: true, fixed, segments };
}

/** null 表示文件没有模板；'INVALID' 表示标记损坏。 */
export function templateSignature(text: string): string | null {
  const info = parseTemplate(text);
  if (!info.ok) return 'INVALID';
  return info.fixed === null ? null : JSON.stringify(info.fixed);
}
