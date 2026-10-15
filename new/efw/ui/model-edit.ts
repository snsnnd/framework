// 页面内模型编辑的共用规则。引用关系一律来自后端 analyze 的 usage，界面不自行推导。
import type { Analysis, Diagnostic, Model, UsageRef } from './types';

export const ID_RE = /^[a-z][a-z0-9_]{0,23}$/;
export const TYPES = ['float', 'int', 'bool'] as const;
export const ITEMS = ['uint8_t', 'int8_t', 'uint16_t', 'int16_t', 'uint32_t', 'int32_t', 'float'] as const;
export const POLICIES = ['drop_oldest', 'drop_newest'] as const;
export const POLICY_LABEL: Record<string, string> = { drop_oldest: '丢弃最旧', drop_newest: '丢弃最新' };

export type Category = 'signals' | 'inputs' | 'outputs' | 'events' | 'queues';
// flows / machines 也能增删改，但没有 usage 引用分析
export type ListKey = Category | 'flows' | 'machines';

/** 新的信号/输入/输出/事件/队列的初始字段（默认值与后端校验一致）。 */
export function newItem(category: Category, id: string, label: string): Record<string, unknown> {
  const name = { id, label: label || id };
  if (category === 'signals') return { ...name, type: 'float', init: 0, unit: '', tune: null };
  if (category === 'events') return name;
  if (category === 'queues') return { ...name, item: 'uint16_t', capacity: 8, policy: 'drop_oldest' };
  if (category === 'outputs') return { ...name, type: 'float', unit: '' };
  return { ...name, type: 'float', unit: '', sim: { kind: 'const', value: 0 } };
}

/** 后端诊断使用的路径前缀：信号与事件/队列不同。 */
export function diagPrefix(category: Category, id: string): string {
  return category === 'signals' ? `signals/${id}` : `comms/${category}/${id}`;
}

export function suggestId(prefix: string, taken: readonly string[]): string {
  const used = new Set(taken);
  for (let i = 1; i < 10000; i++) {
    const candidate = `${prefix}_${i}`.slice(0, 24);
    if (!used.has(candidate)) return candidate;
  }
  return `${prefix}_x`.slice(0, 24);
}

export function idProblem(id: string, taken: readonly string[]): string {
  if (!id) return '请填写标识符';
  if (!ID_RE.test(id)) return '标识符需小写字母开头，只含小写字母、数字、下划线，最长 24 位';
  if (taken.includes(id)) return '同一类对象里标识符必须唯一';
  return '';
}

export interface RefGroup { role: string; refs: UsageRef[] }

/** 引用分组：信号看写入/读取，事件看发出/消费。 */
export function refGroups(analysis: Analysis | null, category: Category, id: string): RefGroup[] {
  if (category === 'signals') {
    const entry = analysis?.usage.signals?.[id];
    if (!entry) return [];
    return [{ role: '被写入', refs: entry.writers ?? [] }, { role: '被读取', refs: entry.readers ?? [] }].filter((g) => g.refs.length);
  }
  if (category === 'events') {
    const entry = analysis?.usage.events?.[id];
    if (!entry) return [];
    return [{ role: '被发出', refs: entry.emitters ?? [] }, { role: '被消费', refs: entry.consumers ?? [] }].filter((g) => g.refs.length);
  }
  if (category === 'inputs' || category === 'outputs') {
    const entry = analysis?.usage[category]?.[id];
    if (!entry) return [];
    return [{ role: category === 'inputs' ? '被读取步骤' : '被写入步骤', refs: entry.steps ?? [] }].filter((g) => g.refs.length);
  }
  return [];
}

export function describeRef(ref: UsageRef): string {
  if ('flow' in ref) return `数据流 ${ref.flow} 的步骤 ${ref.step}`;
  if ('state' in ref) return `状态 ${ref.machine} / ${ref.state}`;
  return `转换 ${ref.machine} / ${ref.transition}`;
}

export function patchItem(model: Model, key: ListKey, id: string, patch: Record<string, unknown>): Model {
  const list = model[key] as { id: string }[];
  return { ...model, [key]: list.map((item) => (item.id === id ? { ...item, ...patch } : item)) };
}

export function appendItem(model: Model, key: ListKey, item: Record<string, unknown>): Model {
  return { ...model, [key]: [...(model[key] as unknown[]), item] };
}

export function removeItem(model: Model, key: ListKey, id: string): Model {
  return { ...model, [key]: (model[key] as { id: string }[]).filter((item) => item.id !== id) };
}

export function fail(message: string, hint = ''): Diagnostic[] {
  return [{ level: 'error', at: 'model', message, hint }];
}