// 调试通知的归约：把 debug.status / debug.frames 变成界面状态。帧字段见 docs/04。
import type { Manifest, Snapshot, TransitionEvent } from './types';

export const SERIES_LIMIT = 1500;
export const TRANSITION_LIMIT = 100;

export interface DebugState {
  session: string | null;
  kind: string;
  state: string;
  t: number;
  speed: number;
  end: number | null;
  message: string;
  warning: boolean;
  manifest: Manifest | null;
  latest: Snapshot | null;
  series: Snapshot[];
  transitions: TransitionEvent[];
  params: Record<string, number> | null;
  ack: { command: string; ok: boolean; message: string } | null;
}

export const EMPTY_DEBUG: DebugState = {
  session: null, kind: '', state: 'idle', t: 0, speed: 1, end: null, message: '', warning: false,
  manifest: null, latest: null, series: [], transitions: [], params: null, ack: null,
};

export const DEBUG_FINISHED = ['stopped', 'error', 'ended'];

export function applyDebugEvent(state: DebugState, event: { event: string; [k: string]: unknown }): DebugState {
  if (event.event === 'debug.status') {
    return {
      ...state,
      state: String(event.state ?? state.state),
      t: Number(event.t ?? state.t),
      speed: Number(event.speed ?? state.speed),
      message: String(event.message ?? ''),
      warning: Boolean(event.warning),
      end: event.end === undefined ? state.end : Number(event.end),
    };
  }
  if (event.event !== 'debug.frames') return state;
  let next = state;
  for (const frame of (event.frames as Record<string, unknown>[]) ?? []) {
    if (frame.e === 'snap') {
      const snap = frame as unknown as Snapshot;
      next = {
        ...next, t: snap.t, latest: snap,
        series: next.series.length >= SERIES_LIMIT ? [...next.series.slice(1), snap] : [...next.series, snap],
      };
    } else if (frame.e === 'trans') {
      next = { ...next, transitions: [...next.transitions, frame as unknown as TransitionEvent].slice(-TRANSITION_LIMIT) };
    } else if (frame.e === 'params') {
      next = { ...next, params: { ...(next.params ?? {}), ...(frame.p as Record<string, number>) } };
    } else if (frame.e === 'ack' || frame.e === 'err') {
      next = { ...next, ack: { command: String(frame.c ?? ''), ok: frame.e === 'ack', message: String(frame.msg ?? '') } };
    }
  }
  return next;
}
