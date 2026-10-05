import { useEffect, useState } from 'react';

interface Props {
  value: string | number;
  onCommit: (raw: string) => void;
  label: string;
  kind?: 'text' | 'number' | 'select';
  options?: { value: string; label: string }[];
  step?: number | 'any';
  min?: number;
  max?: number;
  placeholder?: string;
  /** 下拉未选择时显示的占位项文案（仅当当前值为空时出现）。 */
  emptyLabel?: string;
  disabled?: boolean;
  className?: string;
  /** 提交被拒绝时由父级递增，强制回滚到模型值。 */
  resetKey?: number;
  /** 每次输入都同步给父级（新增表单用：点“添加”时能读到最新值）。 */
  liveCommit?: boolean;
}

/** 行内编辑：本地草稿，失焦或选择时提交；外部值变化时同步但不抢焦点。 */
export function CellInput({ value, onCommit, label, kind = 'text', options, step, min, max, placeholder, emptyLabel = '选择…', disabled, className, resetKey, liveCommit }: Props) {
  const [draft, setDraft] = useState(() => String(value));
  useEffect(() => setDraft(String(value)), [value, resetKey]);
  const commit = () => {
    if (draft === String(value)) return;
    if (kind === 'number') {
      if (draft.trim() === '' || !Number.isFinite(Number(draft))) { setDraft(String(value)); return; }
    }
    onCommit(draft);
  };
  if (kind === 'select') {
    return <select className={`input cell ${className ?? ''}`} aria-label={label} value={draft} disabled={disabled}
      onChange={(e) => { setDraft(e.target.value); onCommit(e.target.value); }}>
      {/* 没有占位项时浏览器会显示第一项，看起来像已经选好了 */}
      {draft === '' && <option value="">{emptyLabel}</option>}
      {options?.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>;
  }
  return <input className={`input cell ${className ?? ''}`} aria-label={label} type={kind} step={step} min={min} max={max}
    placeholder={placeholder} value={draft} disabled={disabled}
    onChange={(e) => { setDraft(e.target.value); if (liveCommit) onCommit(e.target.value); }} onBlur={commit}
    onKeyDown={(e) => { if (e.key === 'Enter') (e.target as HTMLInputElement).blur(); }} />;
}