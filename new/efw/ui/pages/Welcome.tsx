import { useEffect, useState } from 'react';
import { call, isDesktop, pickDirectory } from '../rpc';
import { forgetRecent, useStore } from '../store';
import type { Template } from '../types';

export function Welcome() {
  const { open, create, busy, error, recent: readRecentProjects } = useStore();
  const [recent, setRecent] = useState(() => readRecentProjects());
  const [templates, setTemplates] = useState<Template[] | null>(null);   // null = 还在取模板
  const [tpl, setTpl] = useState('thermostat');
  const [path, setPath] = useState('');

  useEffect(() => {
    void call<Template[]>('templates.list').then(setTemplates).catch((e) => { setTemplates([]); setLoadError((e as Error).message); });
    // 打开失败要从最近列表里拿掉，否则下次进来还会指向一个坏路径
    setRecent(readRecentProjects());
  }, [error, readRecentProjects]);
  const [loadError, setLoadError] = useState('');

  const name = path.split(/[\\/]/).filter(Boolean).pop() ?? '';
  const valid = /^[a-z][a-z0-9_]{0,23}$/.test(name);
  // 绝对路径：POSIX 的 /…、Windows 的 C:\… 与 UNC 的 \\…
  const absolute = /^\//.test(path) || /^[A-Za-z]:[\\/]/.test(path) || /^\\\\/.test(path);

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
            {/* 模板列表要等一次后端往返；这段时间给骨架和一句说明，别留一块空白 */}
            {templates === null ? <>
              <div className="grid two">
                {[0, 1, 2, 3].map((i) => <div key={i} className="tpl-skeleton" aria-hidden="true" />)}
              </div>
              <p className="sub">正在取模板…</p>
            </> : templates.length === 0 ? <p className="sub">没有可用模板。可以直接打开一个已有项目，或检查后端服务是否在运行。</p> : <div className="grid two">
              {templates.map((t) => (
                <button key={t.id} className="tpl" aria-pressed={tpl === t.id} onClick={() => setTpl(t.id)}>
                  <span className="t">{t.label}</span>
                  <span className="d">{t.text}</span>
                </button>
              ))}
            </div>}
            <div className="row">
              <input className="input id" placeholder="项目目录，例如 /home/me/apps/heater" value={path} onChange={(e) => setPath(e.target.value)} aria-label="项目目录" />
              {isDesktop() && <button className="btn" onClick={() => { void pickDirectory().then((dir) => { if (dir) setPath(dir); }); }}>浏览…</button>}
              <button className="btn primary" disabled={busy || !path || !absolute || !valid}
                title={!path ? '先选一个目录' : !absolute ? '需要绝对路径，例如 /home/me/apps/heater'
                  : !valid ? '目录名将作为项目标识：小写字母开头，只含小写字母、数字与下划线' : ''}
                onClick={() => void create(path, name, tpl)}>创建</button>
              <button className="btn" disabled={busy || !path} onClick={() => void open(path)}>打开已有</button>
            </div>
            {path && !valid && <p className="sub">目录名将作为项目标识：小写字母开头，只含小写字母、数字、下划线（最长 24）。</p>}
            {recent.length > 0 && <div className="recent">
              <h3 className="sub">最近打开</h3>
              <ul>
                {recent.map((item) => <li key={item.path}>
                  <button className="recent-item" disabled={busy} onClick={() => void open(item.path)}>
                    <span>{item.name}</span><span className="id sub">{item.path}</span>
                  </button>
                  <button className="btn ghost" aria-label={`忘记 ${item.name}`} title="从最近列表移除"
                    onClick={() => { forgetRecent(item.path); setRecent(readRecentProjects()); }}>×</button>
                </li>)}
              </ul>
            </div>}
            {loadError && <p className="diag error" role="alert">{loadError}</p>}
            <p className="sub">已有的项目目录也可以直接点“打开已有”。项目里的 efw.json 是应用的完整描述，src/ 与 board/ 永远归你。</p>
            {error && <p className="err-text">{error}</p>}
          </div>
        </section>
      </div>
    </div>
  );
}
