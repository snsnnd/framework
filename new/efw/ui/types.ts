// 与后端字段一一对应（docs/02、docs/04）。界面只读这些结构，不自行推导。
export interface Signal { id: string; label: string; type: string; init: number; unit: string; tune: { min: number; max: number } | null }
export interface IoPoint { id: string; label: string; type: string; unit: string }
export interface Step { id: string; kind: string; [k: string]: unknown }
export interface Flow { id: string; label: string; period_ms: number; steps: Step[] }
export interface State { id: string; label: string; run: string[]; set: Record<string, number>; on_enter?: string; on_exit?: string }
export interface Transition { id: string; from: string; to: string; on: Record<string, unknown> }
export interface Machine { id: string; label: string; initial: string; states: State[]; transitions: Transition[] }
export interface Queue { id: string; label: string; item: string; capacity: number; policy: string }
export interface Model {
  version: number; name: string; tick_ms: number;
  limits?: { event_queue?: number };
  signals: Signal[]; inputs: IoPoint[]; outputs: IoPoint[];
  events: { id: string; label: string }[]; queues: Queue[];
  flows: Flow[]; machines: Machine[];
}
export interface Diagnostic { level: 'error' | 'warn' | 'info'; at: string; message: string; hint: string }
export interface PlanItem { id: string; label: string; kind: string; period_ms: number; steps: number; controlled_by: string | null }
export interface FnInfo { name: string; kind: string; role: string; file: string; signature: string; defined: boolean; mismatch: string | null }
export type UsageRef = { flow: string; step: string } | { machine: string; state: string } | { machine: string; transition: string };
export interface Analysis {
  ok: boolean; hash: string; diagnostics: Diagnostic[]; plan: PlanItem[]; functions: FnInfo[];
  usage: {
    signals?: Record<string, { writers: UsageRef[]; readers: UsageRef[] }>;
    events?: Record<string, { emitters: UsageRef[]; consumers: UsageRef[] }>;
  };
  memory: { total: number; parts: { name: string; bytes: number }[] };
}
export interface Opened { path: string; model: Model; layout: unknown; revision: string; files: string[] }
export interface Template { id: string; label: string; text: string; features: string[] }

// ---- 调试：与目标 JSON 帧和 manifest 一一对应（docs/04） ----
export interface FlowStat { on: number; run: number; miss: number; over: number; err: number; late: number; max_late: number; us: number; max_us: number }
export interface QueueStat { n: number; cap: number; push: number; drop: number; hw: number }
export interface Snapshot {
  t: number; s: Record<string, number>; o: Record<string, number>;
  f: Record<string, FlowStat>; q: Record<string, QueueStat>;
  m: Record<string, { s: string; since: number }>; forced: string[]; od?: number;
}
export interface TransitionEvent { t: number; m: string; from: string; to: string; by: string }
export interface Tunable { key: string; label: string; value: number; min: number; max: number; kind: 'param' | 'signal' }
export interface Manifest {
  hash: string; name: string; tick_ms: number;
  signals: { id: string; label: string; type: string; unit: string; tune: { min: number; max: number } | null }[];
  inputs: { id: string; label: string; type: string; unit: string }[];
  outputs: { id: string; label: string; type: string; unit: string }[];
  events: { id: string; label: string }[];
  queues: { id: string; label: string; item: string; capacity: number }[];
  flows: { id: string; label: string; period_ms: number }[];
  machines: { id: string; label: string; initial: string; states: { id: string; label: string }[] }[];
  params: Tunable[];
}
export interface Run { name: string; size: number; kind: string; hash: string; started: string }
