import type { Model } from '../types';

// 概念速览：一张图说清五个概念怎么协作。数字与名称都来自模型，不描述框架内部实现。
export function ConceptMap({ model, running }: { model: Model; running: string | null }) {
  const inputs = model.inputs.slice(0, 2);
  const outputs = model.outputs.slice(0, 2);
  const signals = model.signals.slice(0, 3);
  const flow = model.flows[0];
  return (
    <div className="concept">
      <svg viewBox="0 0 720 190" className="concept-svg" role="img"
        aria-label="硬件输入进入数据流，数据流读写共享信号并驱动硬件输出；状态机决定哪些数据流运行；事件用于抢占与通知">
        <defs>
          <marker id="cm-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="context-stroke" />
          </marker>
        </defs>

        <g className="cm-node">
          <rect x="8" y="60" width="96" height="58" rx="6" />
          <text x="56" y="84" textAnchor="middle">硬件输入</text>
          <text x="56" y="102" textAnchor="middle" className="cm-sub">{inputs.length ? inputs.map((i) => i.id).join('、') : '（无）'}</text>
        </g>

        <g className="cm-node cm-flow">
          <rect x="152" y="46" width="150" height="86" rx="6" />
          <text x="227" y="72" textAnchor="middle">数据流（周期任务）</text>
          <text x="227" y="92" textAnchor="middle" className="cm-sub">{flow ? `${flow.label} · ${flow.period_ms} ms` : '（无）'}</text>
          <text x="227" y="112" textAnchor="middle" className="cm-sub">{flow ? `${flow.steps.length} 个步骤按顺序执行` : ''}</text>
        </g>

        <g className="cm-node cm-signal">
          <rect x="350" y="8" width="150" height="52" rx="6" />
          <text x="425" y="30" textAnchor="middle">信号（共享值）</text>
          <text x="425" y="48" textAnchor="middle" className="cm-sub">{signals.length ? signals.map((s) => s.id).join('、') : '（无）'}</text>
        </g>

        <g className="cm-node">
          <rect x="616" y="60" width="96" height="58" rx="6" />
          <text x="664" y="84" textAnchor="middle">硬件输出</text>
          <text x="664" y="102" textAnchor="middle" className="cm-sub">{outputs.length ? outputs.map((o) => o.id).join('、') : '（无）'}</text>
        </g>

        <g className="cm-node cm-machine">
          <rect x="152" y="150" width="348" height="34" rx="6" />
          <text x="326" y="172" textAnchor="middle">状态机（决定哪些数据流运行）</text>
        </g>

        <g className="cm-node cm-event">
          <rect x="528" y="150" width="184" height="34" rx="6" />
          <text x="620" y="172" textAnchor="middle">事件 / 队列（通知与批量）</text>
        </g>

        <g className="cm-edge">
          <path d="M104 89 H148" markerEnd="url(#cm-arrow)" />
          <path d="M302 72 Q326 42 346 34" markerEnd="url(#cm-arrow)" />
          <path d="M500 34 H592 Q616 34 616 58" markerEnd="url(#cm-arrow)" />
          <path d="M230 150 V136" markerEnd="url(#cm-arrow)" />
          <path d="M302 112 Q420 167 524 167" markerEnd="url(#cm-arrow)" />
        </g>
        <g className="cm-label">
          <text x="126" y="80" textAnchor="middle">读</text>
          <text x="326" y="30" textAnchor="middle">写</text>
          <text x="556" y="26" textAnchor="middle">写硬件</text>
          <text x="252" y="146" textAnchor="start">启停</text>
          <text x="414" y="158" textAnchor="middle">发事件</text>
        </g>
      </svg>
      <p className="concept-legend sub">
        一句话：<span className="id">硬件输入</span> 被 <span className="id">数据流</span> 周期性地取进来，算完写进
        <span className="id"> 共享信号 </span>再驱动 <span className="id">硬件输出</span>；
        <span className="id">状态机</span> 决定此刻跑哪几条数据流，<span className="id">事件</span> 用来抢占与通知。
        {running && <> 现在处于 <strong>{running}</strong>。</>}
      </p>
    </div>
  );
}