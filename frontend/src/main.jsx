import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';
import './style.css';

const fmt = n => (n ?? 0).toLocaleString();
async function api(path, options) {
  const response = await fetch('/api' + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`);
  }
  return response.json();
}
function App() {
  const [jobs, setJobs] = useState([]), [selected, setSelected] = useState(null);
  const [file, setFile] = useState(null), [uploading, setUploading] = useState(false);
  const [error, setError] = useState(''), [errors, setErrors] = useState({items: [], total: 0});
  const [offset, setOffset] = useState(0);
  const input = useRef();
  const job = jobs.find(j => j.id === selected);
  useEffect(() => {
    let active = true, timer;
    async function refresh() {
      try {
        const result = await api('/jobs');
        if (active) {setJobs(result); setSelected(old => old || result[0]?.id); setError('');}
      } catch (e) {if (active) setError(e.message);}
      if (active) timer = setTimeout(refresh, 1500);
    }
    refresh();
    return () => {active = false; clearTimeout(timer);};
  }, []);
  useEffect(() => {setOffset(0); setErrors({items: [], total: 0});}, [selected]);
  useEffect(() => {
    if (!selected) return;
    let active = true;
    api(`/jobs/${selected}/errors?offset=${offset}&limit=20`).then(data => {if (active) setErrors(data);}).catch(e => {if (active) setError(e.message);});
    return () => {active = false;};
  }, [selected, offset, job?.invalid]);
  async function upload(event) {
    event.preventDefault(); if (!file) return;
    setUploading(true); setError('');
    try {
      const data = new FormData(); data.append('file', file);
      const result = await api('/jobs', {method: 'POST', body: data});
      const fresh = await api(`/jobs/${result.id}`);
      setJobs(old => [fresh, ...old.filter(j => j.id !== fresh.id)]);
      setSelected(result.id); setFile(null); input.current.value = '';
    } catch (e) {setError(e.message);} finally {setUploading(false);}
  }
  const busy = job && ['queued', 'running'].includes(job.state);
  return <div className="shell">
    <aside><a className="brand" href="/">◈ <span>signal<span className="brand-dot">.</span></span></a><div className="workspace-label">INTELLIGENCE WORKSPACE</div><div className="nav-active">↳ &nbsp; Feed ingestion</div><p className="aside-note">Turn incoming feeds into<br/>trusted intelligence.</p><div className="aside-bottom"><span className="dot"/> Background processing</div></aside>
    <main><header><span>Workspace <span className="slash">/</span> Threat intelligence</span><span className="tag">ASSESSMENT PROJECT</span></header>
    <div className="heading"><div><p className="eyebrow">COLLECT · VALIDATE · CONSOLIDATE</p><h1>Feed ingestion</h1><p className="muted">Bring your indicators together. Keep the noise out.</p></div><span className="pill">5 supported types</span></div>
    {error && <div role="alert" className="alert">{error}</div>}
    <div className="grid"><section className="card upload"><div className="section-title"><span className="step">01</span><h2>Import a threat feed</h2></div><p className="muted">CSV files are validated and merged in the background.</p>
      <form onSubmit={upload}><label className="dropzone"><span className="upload-icon">↑</span><strong>{file ? file.name : 'Choose your CSV file'}</strong><span>{file ? `${(file.size / 1024).toFixed(1)} KB · Ready to import` : 'Select a file to get started · up to 1 GB'}</span><input ref={input} type="file" accept=".csv,text/csv" onChange={e => setFile(e.target.files[0] || null)} disabled={uploading}/></label><button className="primary" disabled={!file || uploading}>{uploading ? 'Uploading…' : 'Start ingestion'} <span>↗</span></button></form>
      <div className="schema"><h3>EXPECTED COLUMNS</h3><code>indicator, type, confidence,<br/>source, first_seen</code><div className="chips">{['ipv4', 'domain', 'url', 'md5', 'sha256'].map(t => <span key={t}>{t}</span>)}</div></div>
    </section>
    <section className="card activity"><div className="section-title"><span className="step">02</span><h2>Ingestion activity</h2><span className="count">{jobs.length}</span></div><p className="muted">Progress updates automatically every few seconds.</p>
      <div className="job-list">{!jobs.length && <div className="empty"><span>◎</span><h3>Your first feed starts here</h3><p>Upload a CSV to watch it become intelligence.</p></div>}{jobs.map(j => <button className={'job-row ' + (selected === j.id ? 'selected' : '')} key={j.id} onClick={() => setSelected(j.id)}><span className="file-icon">▤</span><span className="job-name"><strong>{j.filename}</strong><small>{fmt(j.processed)} rows processed · {new Date(j.created_at + 'Z').toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'})}</small></span><span className={'status ' + j.state}>{j.state}</span></button>)}</div>
    </section></div>
    <section className="card results"><div className="section-title"><span className="step">03</span><h2>Feed summary</h2>{job && <span className={'status ' + job.state}>{job.state}</span>}</div>{!job ? <p className="muted">Select an ingestion to explore the results.</p> : <>
      <div className="progress-label"><span>{job.filename}</span><span aria-live="polite">{busy ? `${fmt(job.processed)} rows processed · ${job.state}` : `${fmt(job.processed)} rows processed`}</span></div>
      <div className={'progress ' + (busy ? 'busy' : '')} role="progressbar" aria-label="Ingestion progress" aria-valuetext={busy ? `${fmt(job.processed)} rows processed; total determined at completion` : `${job.state}, ${fmt(job.processed)} rows`}><div style={{width: busy ? '35%' : job.state === 'completed' ? '100%' : '0%'}}/></div>
      {job.error && <p role="alert" className="alert">{job.error}</p>}
      <div className="metrics">{[['New indicators', job.new, 'green'], ['Merged indicators', job.merged, 'blue'], ['Invalid rows', job.invalid, 'orange'], ['Rows processed', job.processed, '']].map(([label, value, color]) => <div key={label}><span className="muted">{label}</span><strong className={color}>{fmt(value)}</strong></div>)}</div>
      <div className="breakdown"><h3>VALID ROWS BY TYPE</h3>{['ipv4', 'domain', 'url', 'md5', 'sha256'].map(t => <div className="type-row" key={t}><code>{t}</code><div className="bar"><div style={{width: `${100 * (job.breakdown[t] || 0) / Math.max(1, job.new + job.merged)}%`}}/></div><strong>{fmt(job.breakdown[t])}</strong></div>)}</div>
      {errors.total > 0 && <div className="validation"><h3>INVALID ROW DETAILS <span>{fmt(errors.total)}</span></h3><div className="table-wrap"><table><thead><tr><th>CSV line</th><th>Reason</th></tr></thead><tbody>{errors.items.map(e => <tr key={e.row_number}><td>{e.row_number}</td><td>{e.reason}</td></tr>)}</tbody></table></div><div className="pagination"><button disabled={!offset} onClick={() => setOffset(n => Math.max(0, n - 20))}>Previous</button><span>{offset + 1}–{Math.min(offset + 20, errors.total)} of {fmt(errors.total)}</span><button disabled={offset + 20 >= errors.total} onClick={() => setOffset(n => n + 20)}>Next</button></div></div>}
    </>}</section><footer>Designed for repeatable ingestion. Duplicates merge; confidence and history stay intact.</footer>
    </main></div>;
}
createRoot(document.getElementById('root')).render(<App/>);
