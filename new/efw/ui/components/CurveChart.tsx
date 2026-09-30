import { useEffect, useRef } from 'react';
import type { Snapshot } from '../types';

export interface Channel { id: string; label: string; unit: string; color: string }
const PAD = { left: 46, right: 10, top: 10, bottom: 20 };

function formatTick(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1000) return value.toFixed(0);
  if (magnitude >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

export function CurveChart({ series, channels, height = 260 }: { series: Snapshot[]; channels: Channel[]; height?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = canvasRef.current;
    const parent = canvas?.parentElement;
    if (!canvas || !parent) return;
    const width = parent.clientWidth || 600;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const css = getComputedStyle(canvas);
    const grid = css.getPropertyValue('--line').trim() || '#333';
    const faint = css.getPropertyValue('--fg-faint').trim() || '#888';
    const plotW = width - PAD.left - PAD.right;
    const plotH = height - PAD.top - PAD.bottom;
    ctx.clearRect(0, 0, width, height);
    const value = (snap: Snapshot, id: string): number | undefined => {
      const raw = snap.s?.[id] ?? snap.o?.[id];
      return typeof raw === 'number' && Number.isFinite(raw) ? raw : undefined;
    };
    if (!series.length || !channels.length) {
      ctx.fillStyle = faint;
      ctx.font = '12px sans-serif';
      ctx.fillText(channels.length ? '等待数据…' : '选择要观察的信号', PAD.left, PAD.top + plotH / 2);
      return;
    }
    const tEnd = series[series.length - 1].t;
    const tStart = series[0].t;
    const span = Math.max(1000, tEnd - tStart);
    let low = Infinity;
    let high = -Infinity;
    for (const snap of series) for (const channel of channels) {
      const v = value(snap, channel.id);
      if (v !== undefined) { low = Math.min(low, v); high = Math.max(high, v); }
    }
    if (!Number.isFinite(low) || !Number.isFinite(high)) { low = 0; high = 1; }
    if (high - low < 1e-9) { low -= 1; high += 1; }
    const pad = (high - low) * 0.1;
    low -= pad; high += pad;
    const x = (t: number) => PAD.left + ((t - tStart) / span) * plotW;
    const y = (v: number) => PAD.top + (1 - (v - low) / (high - low)) * plotH;
    ctx.strokeStyle = grid;
    ctx.fillStyle = faint;
    ctx.font = '11px monospace';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const gy = PAD.top + (plotH * i) / 4;
      ctx.beginPath(); ctx.moveTo(PAD.left, gy); ctx.lineTo(PAD.left + plotW, gy); ctx.stroke();
      ctx.fillText(formatTick(high - ((high - low) * i) / 4), 4, gy + 4);
    }
    ctx.fillText(`${(tStart / 1000).toFixed(1)}s`, PAD.left, height - 6);
    ctx.textAlign = 'right';
    ctx.fillText(`${(tEnd / 1000).toFixed(1)}s`, PAD.left + plotW, height - 6);
    ctx.textAlign = 'left';
    for (const channel of channels) {
      ctx.strokeStyle = css.getPropertyValue(channel.color).trim() || '#888';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      for (const snap of series) {
        const v = value(snap, channel.id);
        if (v === undefined) { started = false; continue; }
        const px = x(snap.t);
        const py = y(v);
        if (started) ctx.lineTo(px, py);
        else { ctx.moveTo(px, py); started = true; }
      }
      ctx.stroke();
    }
  }, [series, channels, height]);
  return <div className="chart" style={{ height }}><canvas ref={canvasRef} /></div>;
}
