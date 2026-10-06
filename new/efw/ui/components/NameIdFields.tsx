import { CellInput } from './CellInput';

/**
 * 新建对象的两个输入框：名称（中文，界面上显示）与标识符（英文小写，进入生成的 C 代码）。
 * 这两个框被反复问“下面那个是什么”，所以标题写清用途，并按 kind 给出真实的 C 名字预览。
 */
export type NameIdKind = 'signal' | 'input' | 'output' | 'event' | 'queue' | 'flow' | 'state' | 'machine';

const C_PREVIEW: Record<NameIdKind, (id: string) => string> = {
  signal: (id) => `g_sig_${id}`,
  input: (id) => `${id}_read()`,
  output: (id) => `${id}_write()`,
  event: (id) => `app_emit_${id}()`,
  queue: (id) => `efw_msgq（队列 ${id}）`,
  flow: (id) => `flow_${id}()`,
  state: (id) => `状态 ${id}（出现在 app_state_* 返回值里）`,
  machine: (id) => `g_m_${id}_states`,
};

export function NameIdFields({ kind, idLabel, nameLabel, id, label, placeholder, liveCommit, disabled, onName, onId, cName }: {
  kind: NameIdKind;
  /** 标识符输入框的无障碍名，保持稳定（测试按它定位）；名称框由它推导。 */
  idLabel: string;
  nameLabel?: string;
  id: string;
  label: string;
  placeholder?: string;
  liveCommit?: boolean;
  disabled?: boolean;
  /** false 时不显示 C 名字预览（种类不好给出准确符号时）。 */
  cName?: boolean;
  onName: (value: string) => void;
  onId: (value: string) => void;
}) {
  return <div className="name-id-fields">
    <label>
      <span className="sub">名称</span>
      <CellInput liveCommit={liveCommit} label={nameLabel ?? idLabel.replace(/标识符$/, '名称')} value={label} onCommit={onName}
        placeholder={placeholder ?? '中文，显示在界面与图上'} />
    </label>
    <label>
      <span className="sub">标识符 <span className="id">英文小写，唯一</span></span>
      <CellInput liveCommit={liveCommit} label={idLabel} value={id} onCommit={onId} className="mono" placeholder="例如 temp / mode" />
    </label>
    <p className="name-id-hint sub">
      名称随便写，只影响显示；标识符会直接进入生成的 C 代码，<strong>创建后不能改</strong>。
      {cName !== false && <span className="c-preview">当前会生成：<code>{C_PREVIEW[kind](id || '你的标识符')}</code></span>}
    </p>
  </div>;
}