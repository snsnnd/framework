// 把后端诊断的 at 路径（见 docs/04）映射到能修它的页面与对象。总览页的“下一步”用它做跳转入口。
import type { FnInfo } from './types';

export type RepairPage = 'flows' | 'machines' | 'comm' | 'code';

export interface Repair {
  page: RepairPage;
  /** comm 页的分类；flows/machines/code 不用。 */
  category?: 'signals' | 'inputs' | 'outputs' | 'events' | 'queues';
  /** machines 页要先选中状态机。 */
  machine?: string;
  /** 页内要选中的对象 id（数据流、状态、转换、通信对象或文件名）。 */
  item?: string;
  /** flows/<id>/<step> 里的步骤 id。 */
  step?: string;
  /** 每次点击都递增，保证重复点同一条也能重新触发。 */
  token: number;
}

/** 跳转意图：token 由 App 分配。 */
export type RepairTarget = Omit<Repair, 'token'>;

const COMMS: Record<string, Repair['category']> = {
  signals: 'signals',
  inputs: 'inputs',
  outputs: 'outputs',
  events: 'events',
  queues: 'queues',
};

/** 诊断路径 → 修复入口。无法定位到具体页面时返回 null（调用方渲染成不可点的提示）。 */
export function repairFor(at: string): RepairTarget | null {
  const parts = at.split('/').filter(Boolean);
  const head = parts[0];
  if (head === 'flows') return { page: 'flows', item: parts[1], step: parts[2] };
  if (head === 'machines') return { page: 'machines', machine: parts[1], item: parts[2] };
  if (COMMS[head]) return { page: 'comm', category: COMMS[head], item: parts[1] };
  return null;
}

/** 缺失的 C 函数 → 代码页的对应文件。 */
export function repairForFunction(fn: FnInfo): RepairTarget {
  return { page: 'code', item: fn.file };
}

export const PAGE_LABEL: Record<RepairPage, string> = {
  flows: '数据流', machines: '状态机', comm: '通信', code: '代码',
};

/** 入口上显示的短说明，例如“数据流 control 的读取步骤”。 */
export function repairHint(repair: RepairTarget): string {
  if (repair.page === 'code') return repair.item ?? '代码页';
  if (repair.page === 'flows') return repair.item ? `数据流 ${repair.item}` : '数据流列表';
  if (repair.page === 'machines') {
    if (!repair.machine) return '状态机列表';
    return repair.item ? `状态机 ${repair.machine} 的 ${repair.item}` : `状态机 ${repair.machine}`;
  }
  const kind = repair.category === 'inputs' ? '输入' : repair.category === 'outputs' ? '输出'
    : repair.category === 'events' ? '事件' : repair.category === 'queues' ? '队列'
      : repair.category === 'signals' ? '信号' : '通信';
  return repair.item ? `${kind} ${repair.item}` : kind;
}