import { useState } from 'react';
import { CellInput } from '../components/CellInput';
import { appendItem, fail, idProblem, patchItem, removeItem, suggestId } from '../model-edit';
import { useStore } from '../store';
import type { Diagnostic, Flow, Model, Step, StepField, StepSpec } from '../types';

function controller(model: Model, flowId: string): string | null {
  const st = model.machines.flatMap((mc) => mc.states.filter((s) => s.run.includes(flowId)).map((s) => `${mc.label}·${s.label}`));
  return st.length ? st.join('、') : null;
}

function options(model: Model, field: StepField): { value: string; label: string }[] | undefined {
  if (field.role === 'signal') return model.signals.map((s) => ({ value: s.id, label: `${s.label || s.id} · ${s.id}` }));
  if (field.role === 'input') return model.inputs.map((s) => ({ value: s.id, label: `${s.label || s.id} · ${s.id}` }));
  if (field.role === 'output') return model.outputs.map((s) => ({ value: s.id, label: `${s.label || s.id} · ${s.id}` }));
  if (field.role === 'event') return model.events.map((s) => ({ value: s.id, label: `${s.label || s.id} · ${s.id}` }));
  if (field.role === 'enum') return field.options?.map((o) => ({ value: o, label: o }));
  return undefined;
}

export function Flows() {
  const { project, analysis, updateModel } = useStore();
  const [pending, setPending] = useState(false);
  const [errors, setErrors] = useState<Diagnostic[]>([]);
  const [openStep, setOpenStep] = useState('');
  const [addingIn, setAddingIn] = useState('');
  const [newStepKind, setNewStepKind] = useState('');
  const [addingFlow, setAddingFlow] = useState(false);
  const [flowLabel, setFlowLabel] = useState('');
  const [flowId, setFlowId] = useState('');
  if (!project) return null;
  const model = project.model;
  const specs = analysis?.step_specs ?? [];
  const [resetToken, setResetToken] = useState(0);
  const flowIds = model.flows.map((f) => f.id);
  const stepIds = (f: Flow) => f.steps.map((s) => s.id);

  async function apply(mutate: (m: Model) => Model) {
    setPending(true);
    try {
      const result = await updateModel(mutate);
      setErrors(result.diagnostics);
      if (!result.ok) setResetToken((token) => token + 1);
      return result.ok;
    } catch (e) {
      setErrors(fail((e as Error).message));
      setResetToken((token) => token + 1);
      return false;
    } finally {
      setPending(false);
    }
  }
  const editFlow = (id: string, patch: Partial<Flow>) => apply((m) => patchItem(m, 'flows', id, patch as Record<string, unknown>));
  const editStep = (flowId2: string, stepId: string, patch: Record<string, unknown>) =>
    apply((m) => {
      const flow = m.flows.find((f) => f.id === flowId2);
      if (!flow) return m;
      return patchItem(m, 'flows', flowId2, {
        steps: flow.steps.map((s) => (s.id === stepId ? { ...s, ...patch } : s)),
      });
    });
  function moveStep(flowId2: string, stepId: string, delta: number) {
    return apply((m) => {
      const flow = m.flows.find((f) => f.id === flowId2);
      if (!flow) return m;
      const index = flow.steps.findIndex((s) => s.id === stepId);
      const target = index + delta;
      if (index < 0 || target < 0 || target >= flow.steps.length) return m;
      const steps = [...flow.steps];
      [steps[index], steps[target]] = [steps[target], steps[index]];
      return patchItem(m, 'flows', flowId2, { steps });
    });
  }
  function removeFlow(id: string) {
    const controlling = model.machines.find((mc) => mc.states.some((s) => s.run.includes(id)));
    if (controlling) {
      setErrors(fail(`数据流“${id}”由状态机 ${controlling.id} 控制，不能删除`, '先在状态机页把它从状态的 run 里移除'));
      return;
    }
    void apply((m) => removeItem(m, 'flows', id)).then((ok) => { if (ok) setOpenStep(''); });
  }
  function removeStep(flowId2: string, stepId: string) {
    void apply((m) => {
      const flow = m.flows.find((f) => f.id === flowId2);
      if (!flow) return m;
      return patchItem(m, 'flows', flowId2, { steps: flow.steps.filter((s) => s.id !== stepId) });
    }).then((ok) => { if (ok) setOpenStep(''); });
  }
  function addStep(flowId2: string, kind: string) {
    const spec = specs.find((s) => s.kind === kind);
    if (!spec) return;
    void apply((m) => {
      const flow = m.flows.find((f) => f.id === flowId2);
      if (!flow) return m;
      const step: Record<string, unknown> = { id: suggestId('step', stepIds(flow)), kind };
      for (const field of spec.fields) {
        // 必填引用先给默认值，否则新步骤会让模型非法、保存被后端拒绝
        if (field.role === 'signal') step[field.name] = m.signals[0]?.id ?? '';
        else if (field.role === 'input') step[field.name] = m.inputs[0]?.id ?? '';
        else if (field.role === 'output') step[field.name] = m.outputs[0]?.id ?? '';
        else if (field.role === 'event') step[field.name] = m.events[0]?.id ?? '';
        else if (field.role === 'call') step[field.name] = `${flow.id}_step`;
        else if (field.role === 'number') step[field.name] = field.default ?? 0;
        else if (field.role === 'enum') step[field.name] = field.options?.[0];
      }
      return patchItem(m, 'flows', flowId2, { steps: [...flow.steps, step] });
    }).then((ok) => { if (ok) { setAddingIn(''); setNewStepKind(''); } });
  }
  function addFlow() {
    const problem = idProblem(flowId, flowIds);
    if (problem) { setErrors(fail(problem)); return; }
    void apply((m) => appendItem(m, 'flows', { id: flowId, label: flowLabel || flowId, period_ms: 10 * (m.tick_ms || 1), steps: [] }))
      .then((ok) => { if (ok) { setAddingFlow(false); setFlowLabel(''); setFlowId(''); } });
  }

  function StepFields({ flow, step, spec }: { flow: Flow; step: Step; spec: StepSpec }) {
    return <div className="step-fields">
      {spec.fields.map((field) => <label key={field.name} className="step-field">
        <span className="sub">{field.label}</span>
        {options(model, field)
          ? <CellInput resetKey={resetToken} label={`${step.id} ${field.label}`} kind="select" options={options(model, field)} value={String(step[field.name] ?? field.default ?? '')} onCommit={(raw) => editStep(flow.id, step.id, { [field.name]: raw })} />
          : <CellInput resetKey={resetToken} label={`${step.id} ${field.label}`} kind="number" step="any" min={field.min ?? undefined} max={field.max ?? undefined} value={Number(step[field.name] ?? field.default ?? 0)} onCommit={(raw) => editStep(flow.id, step.id, { [field.name]: Number(raw) })} />}
      </label>)}
    </div>;
  }

  return <>
    <div><h1>数据流</h1><p className="sub">每个数据流按周期，从上到下依次执行这些步骤。展开一步即可改它的信号与参数。</p></div>
    {errors.map((d, i) => <div key={i} className="diag error" role="alert"><div>{d.message}{d.hint && <p className="hint">{d.hint}</p>}</div></div>)}
    {!model.flows.length && !addingFlow && <p className="empty">还没有数据流。点“新增数据流”创建，或在 efw.json 里配置后重新载入。</p>}
    {model.flows.map((f) => {
      const steps = f.steps;
      return <section className="card" key={f.id} aria-label={`数据流 ${f.id}`}>
        <header>
          <span><strong>{f.label}</strong> <span className="id sub">{f.id}</span></span>
          <span className="row">
            <span className="sub">每</span>
            <CellInput label={`${f.id} 周期`} kind="number" min={1} value={f.period_ms} onCommit={(raw) => editFlow(f.id, { period_ms: Math.max(1, Number(raw)) })} />
            <span className="sub">ms</span>
            <span className="sub">· {controller(model, f.id) ? `在 ${controller(model, f.id)} 运行` : '始终运行'}</span>
            <button className="btn" disabled={pending} onClick={() => setAddingIn(addingIn === f.id ? '' : f.id)}>添加步骤</button>
            <button className="btn danger" disabled={pending} onClick={() => removeFlow(f.id)}>删除</button>
          </span>
        </header>
        {steps.map((s, i) => {
          const spec = specs.find((x) => x.kind === s.kind);
          const open = openStep === `${f.id}/${s.id}`;
          return <div key={s.id} className={`step-row${open ? ' is-open' : ''}`} data-id={s.id}>
            <div className="step-line" onClick={() => setOpenStep(open ? '' : `${f.id}/${s.id}`)} role="button" tabIndex={0}
              onKeyDown={(e) => { if (e.key === 'Enter') setOpenStep(open ? '' : `${f.id}/${s.id}`); }}>
              <span className="no">{i + 1}</span>
              <span className="verb">{spec?.label ?? s.kind}</span>
              <span className="sub">{describeStep(s, specs)}</span>
              <span className="spacer" />
              <button className="btn ghost" disabled={pending || i === 0} aria-label={`${f.id} ${s.id} 上移`} onClick={(e) => { e.stopPropagation(); void moveStep(f.id, s.id, -1); }}>↑</button>
              <button className="btn ghost" disabled={pending || i === steps.length - 1} aria-label={`${f.id} ${s.id} 下移`} onClick={(e) => { e.stopPropagation(); void moveStep(f.id, s.id, 1); }}>↓</button>
              <button className="btn ghost" disabled={pending} aria-label={`${f.id} ${s.id} 删除`} onClick={(e) => { e.stopPropagation(); removeStep(f.id, s.id); }}>×</button>
            </div>
            {open && spec && <StepFields flow={f} step={s} spec={spec} />}
          </div>;
        })}
        {addingIn === f.id && <div className="step-add">
          <span className="sub">新步骤类型</span>
          <select className="input" value={newStepKind} onChange={(e) => setNewStepKind(e.target.value)} aria-label="新步骤类型">
            <option value="">选择…</option>
            {specs.map((s) => <option key={s.kind} value={s.kind}>{s.label}</option>)}
          </select>
          <button className="btn primary" disabled={pending || !newStepKind} onClick={() => addStep(f.id, newStepKind)}>添加</button>
          <button className="btn" onClick={() => { setAddingIn(''); setNewStepKind(''); }}>取消</button>
        </div>}
      </section>;
    })}
    {addingFlow ? <section className="card">
      <header><h2>新增数据流</h2></header>
      <div className="step-add">
        <CellInput liveCommit label="新数据流名称" value={flowLabel} onCommit={setFlowLabel} placeholder="名称" />
        <CellInput liveCommit label="新数据流标识符" value={flowId} onCommit={setFlowId} className="mono" />
        <button className="btn primary" disabled={pending} onClick={addFlow}>添加</button>
        <button className="btn" onClick={() => setAddingFlow(false)}>取消</button>
      </div>
    </section> : <div><button className="btn" onClick={() => { setAddingFlow(true); setFlowId(suggestId('flow', flowIds)); }}>新增数据流</button></div>}
  </>;
}

function describeStep(step: Step, specs: StepSpec[]): string {
  const spec = specs.find((s) => s.kind === step.kind);
  if (!spec) return step.id;
  const parts: string[] = [];
  for (const field of spec.fields) {
    const value = step[field.name];
    if (value === undefined) continue;
    parts.push(`${field.label} ${value}`);
  }
  return parts.length ? parts.join(' · ') : step.id;
}