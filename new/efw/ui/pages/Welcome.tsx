import { useEffect, useState } from 'react';
import { call } from '../rpc';
import { useStore } from '../store';
import type { Template } from '../types';

export function Welcome() {
  const { open, create, busy, error } = useStore();
  const [templates, setTemplates] = useState<Template[]>([]);
  const [tpl, setTpl] = useState('thermostat');
  const [path, setPath] = useState('');

  useEffect(() => { void call<Template[]>('templates.list').then(setTemplates).catch(() => undefined); }, []);

  const name = path.split('/').filter(Boolean).pop() ?? '';
  const valid = /^[a-z][a-z0-9_]{0,23}$/.test(name);

  return (
    <div className="page" style={{ height: '100%' }}>
      <div className="inner" style={{ maxWidth: 720, paddingTop: 48 }}>
        <div>
          <h1>EFW Studio</h1>
          <p className="sub">用能一句话读懂的结构描述嵌入式应用，在电脑上先跑起来，再上真机。</p>
        </div>

        <section className="card">
          <header><h2>新建项目</h2></header>
          <div className="body" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div className="grid two">
              {templates.map((t) => (
                <button key={t.id} className="tpl" aria-pressed={tpl === t.id} onClick={() => setTpl(t.id)}>
                  <span className="t">{t.label}</span>
                  <span className="d">{t.text}</span>
                </button>
              ))}
            </div>
            <div className="row">
              <input className="input id" placeholder="项目目录，例如 /home/me/apps/heater" value={path} onChange={(e) => setPath(e.target.value)} aria-label="项目目录" />
              <button className="btn primary" disabled={busy || !path.startsWith('/') || !valid} onClick={() => void create(path, name, tpl)}>创建</button>
              <button className="btn" disabled={busy || !path} onClick={() => void open(path)}>打开已有</button>
            </div>
            {path && !valid && <p className="sub">目录名将作为项目标识：小写字母开头，只含小写字母、数字、下划线（最长 24）。</p>}
            {error && <p className="err-text">{error}</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
