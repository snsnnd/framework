import type { PlanItem } from '../types';

// 整机时间线：数据全部来自 analyze.plan（任务顺序 = 注册顺序，周期 = period_ms）。
// 这里只做几何计算，不推断调度语义：到点就画一个标记。
const MAX_MARKS = 60;

export interface TimelineProps {
  plan: PlanItem[];
  tick_ms: number;
  /** 正在运行时给出“现在”这一条游标。 */
  now?: number | null;
}

export function Timeline({ plan, tick_ms, now = null }: TimelineProps) {
  const tasks = plan.filter((t) => t.kind === 'flow');
  const system = plan.filter((t) => t.kind !== 'flow');
  if (!tasks.length) return null;
  const periods = tasks.map((t) => t.period_ms);
  const slowest = Math.max(...periods);
  const fastest = Math.min(...periods);
  const span = Math.min(slowest, fastest * MAX_MARKS);
  const marks = (period: number) => {
    const out: number[] = [];
    for (let t = 0; t <= span; t += period) out.push(t);
    return out;
  };
  const x = (t: number) => (t / span) * 100;
  const ticks = Math.round(span / tick_ms);
  const axisEvery = Math.max(1, Math.ceil(ticks / 10));

  return (
    <div className="timeline">
      <div className="timeline-axis" aria-hidden="true">
        <span className="timeline-axis-label">0 ms</span>
        <span className="timeline-ticks">
          {Array.from({ length: Math.floor(ticks / axisEvery) + 1 }, (_, i) => i * axisEvery * tick_ms)
            .filter((t) => t === 0 || t < span)   // 末端由右侧标签标注，避免叠字
            .map((t) => <span key={t} style={{ left: `${x(t)}%` }}>{t}</span>)}
        </span>
        <span className="timeline-axis-label">{span} ms</span>
      </div>

      <ol className="timeline-lanes">
        {tasks.map((task, index) => (
          <li key={task.id} className={`timeline-lane${task.controlled_by ? ' is-gated' : ''}`}>
            <span className="timeline-slot" title={`槽位 ${index + 1}`}>{index + 1}</span>
            <span className="timeline-name">
              <span className="timeline-label">{task.label}</span>
              <span className="id sub">{task.id}</span>
            </span>
            <span className="timeline-track" role="img"
              aria-label={`${task.label} 每 ${task.period_ms} 毫秒执行一次，窗口内 ${marks(task.period_ms).length} 次`}>
              <span className="timeline-tick-marks" aria-hidden="true">
                {marks(task.period_ms).map((t) => <i key={t} style={{ left: `${x(t)}%` }} />)}
              </span>
              {task.controlled_by && <span className="timeline-gate" title={`只有状态机 ${task.controlled_by} 运行时才执行`} />}
              {now !== null && now % span <= span && <span className="timeline-now" style={{ left: `${x(now % span)}%` }} aria-hidden="true" />}
            </span>
            <span className="timeline-facts sub">
              {task.period_ms} ms · {task.steps} 步
              {task.controlled_by ? ` · 受 ${task.controlled_by} 控制` : ' · 始终运行'}
            </span>
          </li>
        ))}
        {system.map((task) => (
          <li key={task.id} className="timeline-lane is-system">
            <span className="timeline-slot">∞</span>
            <span className="timeline-name">
              <span className="timeline-label">{task.label}</span>
              <span className="id sub">{task.id}</span>
            </span>
            <span className="timeline-track"><span className="timeline-tick-marks" aria-hidden="true" /></span>
            <span className="timeline-facts sub">每个 tick · 状态机与事件在这里推进</span>
          </li>
        ))}
      </ol>

      <p className="timeline-legend sub">
        中断每 <span className="id">{tick_ms} ms</span> 触发一次，按槽位顺序检查每个任务，到期就执行一遍；
        {tasks.some((t) => t.controlled_by) ? '带锁的泳道只有对应状态机处于该状态时才执行。' : '所有任务始终执行。'}
        {span < slowest && ` 图上只画了前 ${span} ms（最长周期 ${slowest} ms 未完整显示）。`}
        {now !== null && ' 竖线是当前仿真时间。'}
      </p>
    </div>
  );
}