import React, { useState, useRef } from 'react';
import axios from 'axios';
import { UploadCloud, CheckCircle, AlertCircle, Layers, ArrowUp, ArrowDown, ArrowRight, ArrowLeft, Compass, RotateCcw, Wrench, GitCompareArrows } from 'lucide-react';
import ModelViewer from './ModelViewer';

function App() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [candidates, setCandidates] = useState([]);   // from the auto-search run
  const [customDir, setCustomDir] = useState('');
  // Exact per-direction undercut figures arrive after the main result: the
  // full axis sweep is the slow part of the pipeline and only feeds this
  // panel, so it must not hold up the 3D view.
  const [ranking, setRanking] = useState('idle');     // idle | loading | done
  const fileInputRef = useRef(null);

  const analyze = async (file, direction = null) => {
    const formData = new FormData();
    formData.append('file', file);
    if (direction) formData.append('direction', direction.join(','));

    setLoading(true);
    setError(null);

    try {
      const response = await axios.post('/api/analyze', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setData(response.data);
      // Keep the ranked candidate list from the automatic search so the
      // user can compare directions even after overriding.
      if (!direction) {
        setCandidates(response.data.direction_candidates || []);
        refineRanking(file);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to analyze part.');
    } finally {
      setLoading(false);
    }
  };

  // Second pass: exact undercut counts for every candidate direction. The
  // first response only carries lower bounds for the losing axes (">=N"),
  // which cannot be compared against each other, so this replaces them once
  // the full sweep finishes. Failure is non-fatal — the bounds simply stay.
  const refineRanking = async (file) => {
    setRanking('loading');
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await axios.post('/api/analyze/directions', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      if (res.data?.direction_candidates?.length) {
        setCandidates(res.data.direction_candidates);
      }
    } catch {
      // keep the lower-bound list
    } finally {
      setRanking('done');
    }
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setSelectedFile(file);
    setData(null);
    setCandidates([]);
    setCustomDir('');
    await analyze(file);
  };

  const handleCustomDirection = async () => {
    if (!selectedFile) return;
    const parts = customDir.split(',').map(v => parseFloat(v.trim()));
    if (parts.length !== 3 || parts.some(isNaN) || parts.every(v => Math.abs(v) < 1e-9)) {
      setError("Custom direction must be 'x,y,z' with a non-zero vector");
      return;
    }
    await analyze(selectedFile, parts);
  };

  // The backend returns the primary loop first, then any further CLOSED
  // loops. Report the PRIMARY one: the deliverable is a single continuous
  // parting line, so showing a candidate count as "loops" reads as though we
  // emitted a discontinuous line.
  const partingLines = data?.geometry?.parting_lines || [];
  const primaryLoop = partingLines.find((l) => l.is_primary) || partingLines[0] || null;
  const primaryEdges = primaryLoop?.segments?.length || 0;

  // Validation is reported separately from the score on purpose: a parting
  // line that is not manufacturable must say so, not hide behind a number.
  const plValidation = data?.parting_line?.validation || null;
  const plConfidence = data?.geometry?.parting_line_confidence;
  const plValid = data?.geometry?.parting_line_is_valid;
  const plFailures = plValidation?.checks?.filter((c) => !c.passed) || [];
  const shutoffLength = primaryLoop?.shutoff_length || 0;

  // Tooling: feature groups a DECLARED plan hands to side actions. When
  // this is non-empty the undercut count describes the two main halves
  // only, so the two must always be shown together — a zero bought with
  // side cores is not the same result as a zero that needed none.
  const tooling = data?.tooling || null;
  const requiredActions = tooling?.required_actions || [];
  const hasDelegation = requiredActions.length > 0;
  const alternatives = data?.alternatives || [];

  const formatDirection = (label) => {
    let Icon = null;
    if (label.includes('Z+')) Icon = <ArrowUp size={16} />;
    else if (label.includes('Z-')) Icon = <ArrowDown size={16} />;
    else if (label.includes('X+')) Icon = <ArrowRight size={16} />;
    else if (label.includes('X-')) Icon = <ArrowLeft size={16} />;
    else if (label.includes('Y+')) Icon = <ArrowUp size={16} style={{transform: 'rotate(45deg)'}} />;
    else if (label.includes('Y-')) Icon = <ArrowDown size={16} style={{transform: 'rotate(45deg)'}} />;

    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
        {label.split(' ')[0]} axis {Icon}
      </div>
    );
  };

  return (
    <div className="app-container">
      <div className="dashboard">
        <div className="dashboard-header">
          <h1>DfM Auto-Analyzer</h1>
          <p>AI-driven manufacturability checks</p>
        </div>

        {data ? (
          <button
            type="button"
            onClick={() => fileInputRef.current.click()}
            style={{
              font: 'inherit',
              color: 'inherit',
              padding: '0.75rem',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--glass-border)',
              borderRadius: '8px',
              cursor: 'pointer',
              textAlign: 'center',
              fontSize: '0.875rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '0.5rem'
            }}
          >
            <UploadCloud size={16} /> Upload New Part
          </button>
        ) : (
          <button type="button" className="file-upload" onClick={() => fileInputRef.current.click()}>
            <UploadCloud color="var(--primary)" size={48} style={{ marginBottom: '1rem' }} />
            <h3>Upload CAD Part</h3>
            <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginTop: '0.5rem' }}>
              Drag & drop or click to upload a .stp file
            </p>
          </button>
        )}
        <input
          type="file"
          ref={fileInputRef}
          accept=".stp,.step"
          onChange={handleFileUpload}
          style={{ display: 'none' }}
          aria-label="Upload CAD file"
        />

        {error && (
          <div style={{ color: '#ef4444', background: 'rgba(239, 68, 68, 0.1)', padding: '1rem', borderRadius: '8px', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <AlertCircle size={20} />
            <span>{error}</span>
          </div>
        )}

        {data && (
          <>
            <div className="metrics-grid">
              <div className="metric-card">
                <div className="metric-label">Score</div>
                <div className="metric-value" style={{ color: data.score > 90 ? '#10b981' : '#f59e0b' }}>
                  {data.score.toFixed(1)}/100
                </div>
                <div className="metric-subtext">
                  {data.score > 90 ? 'Excellent moldability' : 'Based on undercuts'}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Total Faces</div>
                <div className="metric-value">{data.total_faces}</div>
                <div className="metric-subtext">Processed CAD geometry</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Best Pull Dir</div>
                <div className="metric-value" style={{ fontSize: '1.25rem' }}>
                  {formatDirection(data.best_direction_label)}
                </div>
                <div className="metric-subtext">
                  {data.is_override ? 'Manual override active' : 'Max area without undercuts'}
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-label">
                  Undercuts{hasDelegation ? ' (main halves)' : ''}
                </div>
                <div className="metric-value" style={{ color: data.undercut_faces > 0 ? '#ef4444' : '#10b981' }}>
                  {data.undercut_faces}
                  {hasDelegation && (
                    <span style={{
                      fontSize: '0.7rem', marginLeft: '0.4rem', padding: '0.1rem 0.35rem',
                      borderRadius: '4px', background: 'rgba(245,158,11,0.18)', color: '#f59e0b',
                      verticalAlign: 'middle', whiteSpace: 'nowrap', display: 'inline-block',
                    }}>
                      +{requiredActions.length} side action{requiredActions.length === 1 ? '' : 's'}
                    </span>
                  )}
                </div>
                <div className="metric-subtext" style={hasDelegation ? { color: '#f59e0b' } : undefined}>
                  {hasDelegation
                    ? `Two main halves only — ${tooling.delegated_area} mm² is formed by separate tooling`
                    : 'Faces trapped in mold'}
                </div>
              </div>
              <div className="metric-card" style={{ gridColumn: 'span 2' }}>
                <div className="metric-label">Main Parting Line</div>
                <div className="metric-value" style={{ color: '#00ffff', fontSize: '1.25rem' }}>
                  {primaryLoop
                    ? `1 ${primaryLoop.is_closed === false ? 'open chain' : 'closed loop'}`
                    : 'Not found'}
                  {primaryLoop && (
                    <span style={{ fontSize: '0.875rem', color: '#94a3b8' }}> ({primaryEdges} edges)</span>
                  )}
                  {typeof plConfidence === 'number' && (
                    <span style={{
                      fontSize: '0.75rem',
                      marginLeft: '0.5rem',
                      padding: '0.1rem 0.4rem',
                      borderRadius: '4px',
                      background: plValid ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                      color: plValid ? '#10b981' : '#ef4444',
                    }}>
                      {plValid ? 'valid' : 'not valid'} · {(plConfidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <div className="metric-subtext">
                  {data.geometry?.parting_line_is_ambiguous
                    ? '⚠️ Top candidates score within 5% — review alternates'
                    : primaryLoop && primaryLoop.is_closed === false
                      ? '⚠️ Not closed — cannot form a mold face'
                      : primaryLoop?.source === 'silhouette'
                        ? 'Clamshell split — derived from the part silhouette'
                        : 'Single continuous loop where core meets cavity'}
                  {shutoffLength > 0 && (
                    <div style={{ color: '#f59e0b', marginTop: '0.25rem' }}>
                      {shutoffLength.toFixed(1)} mm of this loop is a side-action
                      shutoff, not main parting line
                    </div>
                  )}
                </div>
                {/* Failed checks, listed explicitly. Confidence is capped by
                    these rather than averaged with them, so a low number here
                    always has a stated reason. */}
                {plFailures.length > 0 && (
                  <ul style={{
                    margin: '0.5rem 0 0', paddingLeft: '1rem',
                    fontSize: '0.7rem', color: '#fca5a5', lineHeight: 1.5,
                  }}>
                    {plFailures.slice(0, 4).map((c) => (
                      <li key={c.name}>{c.detail || c.name}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <div style={{ marginTop: '1rem' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '0.5rem', color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Compass size={16} /> Mold Direction
              </h3>
              <p style={{ fontSize: '0.75rem', color: '#64748b', marginBottom: '0.75rem' }}>
                Override the pull direction (e.g., to move flash off cosmetic surfaces).
              </p>
              {ranking === 'loading' && (
                <div
                  aria-live="polite"
                  style={{
                    display: 'flex', alignItems: 'center', gap: '0.5rem',
                    fontSize: '0.75rem', color: '#60a5fa', marginBottom: '0.5rem',
                  }}
                >
                  <span className="mini-spinner" aria-hidden="true" />
                  Ranking all directions…
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {candidates.slice(0, 6).map((c) => {
                  const isActive = !data.is_override && c.label === data.best_direction_label;
                  return (
                    <button
                      key={c.label}
                      onClick={() => analyze(selectedFile, c.direction)}
                      disabled={loading}
                      style={{
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                        padding: '0.4rem 0.6rem', borderRadius: '6px', cursor: 'pointer',
                        fontSize: '0.8rem',
                        background: isActive ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255,255,255,0.04)',
                        border: isActive ? '1px solid #3b82f6' : '1px solid var(--glass-border)',
                        color: '#e2e8f0',
                      }}
                    >
                      <span>{c.label}{isActive ? ' (auto-best)' : ''}</span>
                      <span style={{ color: c.undercut_count === 0 && !c.pruned ? '#10b981' : '#f59e0b' }}>
                        {c.pruned ? '≥' : ''}{c.undercut_count} undercuts
                      </span>
                    </button>
                  );
                })}
              </div>
              <div style={{ display: 'flex', gap: '6px', marginTop: '8px' }}>
                <input
                  type="text"
                  value={customDir}
                  onChange={(e) => setCustomDir(e.target.value)}
                  placeholder="custom: x,y,z"
                  aria-label="Custom mold pull direction"
                  autoComplete="off"
                  name="custom-direction"
                  style={{
                    flex: 1, padding: '0.4rem 0.6rem', borderRadius: '6px',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid var(--glass-border)',
                    color: '#e2e8f0', fontSize: '0.8rem',
                  }}
                />
                <button
                  onClick={handleCustomDirection}
                  disabled={loading || !customDir}
                  style={{
                    padding: '0.4rem 0.75rem', borderRadius: '6px', cursor: 'pointer',
                    background: '#3b82f6', color: 'white', border: 'none', fontSize: '0.8rem', fontWeight: 600,
                  }}
                >
                  Apply
                </button>
              </div>
              {data.is_override && (
                <button
                  onClick={() => analyze(selectedFile)}
                  disabled={loading}
                  style={{
                    marginTop: '8px', width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '6px',
                    padding: '0.4rem', borderRadius: '6px', cursor: 'pointer',
                    background: 'rgba(255,255,255,0.05)', border: '1px solid var(--glass-border)',
                    color: '#94a3b8', fontSize: '0.8rem',
                  }}
                >
                  <RotateCcw size={14} /> Reset to auto-detected direction
                </button>
              )}
            </div>

            {/* ── REQUIRED TOOLING ─────────────────────────────────────
                Shown whenever a tooling plan delegates feature groups to side
                actions. It sits directly under the metrics, ABOVE everything
                else, because the undercut count above it describes the two
                main halves only. Delegation always terminates at zero — any
                undercut set vanishes if you hand its faces to other tooling —
                so the count alone means nothing without this panel beside it. */}
            {hasDelegation && (
              <div style={{ marginTop: '1rem' }}>
                <h3 style={{ fontSize: '1rem', marginBottom: '0.25rem', color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Wrench size={16} /> Required Tooling
                </h3>
                <p style={{ fontSize: '0.7rem', color: '#64748b', marginBottom: '0.75rem' }}>
                  Declared in <code style={{ color: '#94a3b8' }}>{tooling.source || 'a tooling plan'}</code>.
                  These groups are formed by separate mechanisms, so the two main
                  halves are not asked to release them.
                </p>

                <div style={{
                  border: '1px solid rgba(245,158,11,0.35)',
                  background: 'rgba(245,158,11,0.08)',
                  borderRadius: '8px', padding: '0.75rem',
                }}>
                  <div style={{
                    fontSize: '0.75rem', color: '#f59e0b', fontWeight: 600,
                    marginBottom: '0.6rem', display: 'flex', gap: '0.4rem', alignItems: 'center',
                  }}>
                    <AlertCircle size={14} />
                    {requiredActions.length} side action{requiredActions.length === 1 ? '' : 's'} on{' '}
                    {tooling.action_axis_count} axis/axes &middot; {tooling.delegated_area} mm² total
                  </div>

                  {requiredActions.map((a) => (
                    <div key={a.name} style={{
                      display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                      gap: '0.5rem', padding: '0.4rem 0',
                      borderTop: '1px solid rgba(255,255,255,0.07)',
                    }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: '0.8rem', color: '#e2e8f0', fontWeight: 600 }}>
                          {a.name}
                        </div>
                        <div style={{ fontSize: '0.7rem', color: '#94a3b8' }}>
                          {a.mechanism} along ({a.action_axis.map((v) => v.toFixed(2)).join(', ')})
                        </div>
                        {a.rationale && (
                          <div style={{ fontSize: '0.65rem', color: '#64748b', marginTop: '0.2rem', lineHeight: 1.4 }}>
                            {a.rationale}
                          </div>
                        )}
                      </div>
                      <div style={{ textAlign: 'right', whiteSpace: 'nowrap', fontSize: '0.7rem', color: '#94a3b8' }}>
                        <div style={{ color: '#e2e8f0', fontWeight: 600 }}>{a.area} mm²</div>
                        <div>{a.face_count} faces</div>
                      </div>
                    </div>
                  ))}

                  {tooling.preferred_direction_note && (
                    <div style={{
                      fontSize: '0.65rem', color: '#64748b', marginTop: '0.5rem',
                      paddingTop: '0.5rem', borderTop: '1px solid rgba(255,255,255,0.07)',
                    }}>
                      Pull direction: {tooling.preferred_direction_note}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ── ALTERNATIVE CONFIGURATIONS ───────────────────────────
                Present so the choice is visible rather than asserted. The
                undercut column alone does not decide between these: once side
                actions are allowed, what discriminates is how much of the part
                the two main halves still form, and how many extra motions the
                mold needs. Both are shown. */}
            {alternatives.length > 0 && (
              <div style={{ marginTop: '1rem' }}>
                <h3 style={{ fontSize: '1rem', marginBottom: '0.25rem', color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <GitCompareArrows size={16} /> Alternative Configurations
                </h3>
                <p style={{ fontSize: '0.7rem', color: '#64748b', marginBottom: '0.75rem' }}>
                  Compare the whole row, not the undercut column — a lower count
                  may simply mean more was handed to side actions.
                </p>

                <div style={{ fontSize: '0.7rem' }}>
                  <div style={{
                    display: 'grid', gridTemplateColumns: '1.4fr 0.9fr 1fr',
                    gap: '0.4rem', color: '#64748b', paddingBottom: '0.35rem',
                    borderBottom: '1px solid rgba(255,255,255,0.1)',
                  }}>
                    <span>Direction</span>
                    <span style={{ textAlign: 'right' }}>Undercuts</span>
                    <span style={{ textAlign: 'right' }}>Main halves &middot; axes</span>
                  </div>

                  {/* The configuration actually selected, for comparison. */}
                  <div style={{
                    display: 'grid', gridTemplateColumns: '1.4fr 0.9fr 1fr',
                    gap: '0.4rem', padding: '0.4rem 0', alignItems: 'center',
                    borderBottom: '1px solid rgba(255,255,255,0.06)',
                    background: 'rgba(59,130,246,0.08)',
                  }}>
                    <span style={{ color: '#3B82F6', fontWeight: 600 }}>
                      {data.best_direction_label} <span style={{ fontSize: '0.6rem' }}>SELECTED</span>
                    </span>
                    <span style={{ textAlign: 'right', color: data.undercut_faces > 0 ? '#ef4444' : '#10b981' }}>
                      {data.undercut_faces}
                    </span>
                    <span style={{ textAlign: 'right', color: '#94a3b8' }}>
                      {typeof tooling?.main_half_fraction === 'number'
                        ? `${(tooling.main_half_fraction * 100).toFixed(0)}%`
                        : data.areas?.total
                          ? `${(100 * ((data.areas.core || 0) + (data.areas.cavity || 0) - (data.areas.undercut || 0)) / data.areas.total).toFixed(0)}%`
                          : '—'}
                    </span>
                  </div>

                  {alternatives.map((a) => (
                    <React.Fragment key={a.label}>
                      <div style={{
                        display: 'grid', gridTemplateColumns: '1.4fr 0.9fr 1fr',
                        gap: '0.4rem', padding: '0.4rem 0', alignItems: 'center',
                        borderBottom: a.if_delegated ? 'none' : '1px solid rgba(255,255,255,0.06)',
                      }}>
                        <span style={{ color: '#cbd5e1', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {a.label}
                          {!a.needs_declared_plan && (
                            <span style={{ color: '#10b981', fontSize: '0.6rem', marginLeft: '0.3rem' }}>
                              NO SIDE CORE
                            </span>
                          )}
                        </span>
                        <span style={{ textAlign: 'right', color: a.undercut_count > 0 ? '#f59e0b' : '#10b981' }}>
                          {a.undercut_count}
                          {a.undercut_area > 0 && (
                            <span style={{ color: '#64748b', fontSize: '0.6rem' }}>
                              {' '}({a.undercut_area})
                            </span>
                          )}
                        </span>
                        <span style={{ textAlign: 'right', color: '#94a3b8' }}>
                          {(a.main_half_fraction * 100).toFixed(0)}%
                          <span style={{ color: '#64748b', fontSize: '0.6rem' }}>
                            {' '}&middot; {a.extra_action_axes} ax
                          </span>
                        </span>
                      </div>

                      {/* The same configuration with ITS OWN trapped regions
                          delegated — the like-for-like comparison, since the
                          primary also reached zero by delegating. Computed
                          from the region grouper, not assumed. */}
                      {a.if_delegated && (
                        <div style={{
                          display: 'grid', gridTemplateColumns: '1.4fr 0.9fr 1fr',
                          gap: '0.4rem', padding: '0.3rem 0 0.4rem 0.8rem', alignItems: 'center',
                          borderBottom: '1px solid rgba(255,255,255,0.06)',
                          fontSize: '0.65rem',
                        }}>
                          <span style={{ color: '#64748b' }}>
                            ↳ with {a.if_delegated.region_count} region
                            {a.if_delegated.region_count === 1 ? '' : 's'} delegated
                            {Object.keys(a.if_delegated.mechanisms || {}).length > 0 && (
                              <span> ({Object.entries(a.if_delegated.mechanisms)
                                .map(([m, n]) => `${n}× ${m}`).join(', ')})</span>
                            )}
                          </span>
                          <span style={{ textAlign: 'right', color: '#10b981' }}>0</span>
                          <span style={{ textAlign: 'right', color: '#94a3b8' }}>
                            {(a.if_delegated.main_half_fraction * 100).toFixed(0)}%
                            <span style={{ color: '#64748b' }}>
                              {' '}&middot; {a.if_delegated.extra_action_axes} ax
                            </span>
                          </span>
                        </div>
                      )}
                    </React.Fragment>
                  ))}
                </div>

                {alternatives.some((a) => a.would_need_further_actions) && (
                  <p style={{ fontSize: '0.65rem', color: '#64748b', marginTop: '0.5rem', lineHeight: 1.5 }}>
                    Rows with a non-zero undercut count would need further side
                    actions of their own to reach zero — the count is what a
                    straight pull leaves, not a defect of the configuration.
                  </p>
                )}
              </div>
            )}

            <div style={{ marginTop: '1rem' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '0.25rem', color: '#e2e8f0' }}>Surface Split</h3>
              <p style={{ fontSize: '0.7rem', color: '#64748b', marginBottom: '0.75rem' }}>
                Share of part surface area formed by each mold half.
              </p>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', fontSize: '0.875rem' }}>
                {[
                  { key: 'core', label: 'Core', color: '#60a5fa', count: data.core_faces },
                  { key: 'cavity', label: 'Cavity', color: '#fbbf24', count: data.cavity_faces },
                  { key: 'undercut', label: 'Undercut', color: '#ef4444', count: data.undercut_faces },
                ].map(({ key, label, color, count }) => {
                  const total = data.areas?.total || 0;
                  const area = data.areas?.[key] || 0;
                  const pct = total > 0 ? (100 * area) / total : 0;
                  return (
                    <div key={key}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                        <span style={{ color: '#94a3b8' }}>{label}</span>
                        <span>
                          <strong style={{ color, fontVariantNumeric: 'tabular-nums' }}>{pct.toFixed(1)}%</strong>
                          <span style={{ fontSize: '0.75rem', color: '#64748b' }}> · {count} faces</span>
                        </span>
                      </div>
                      <div
                        style={{
                          height: '4px', marginTop: '4px', borderRadius: '2px',
                          background: 'rgba(255,255,255,0.06)', overflow: 'hidden',
                        }}
                      >
                        <div style={{ width: `${pct}%`, height: '100%', background: color }} />
                      </div>
                    </div>
                  );
                })}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '0.25rem' }}>
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ color: '#94a3b8' }}>Low draft</span>
                    <span style={{ fontSize: '10px', color: '#64748b' }}>(Draft angle &lt; 1°)</span>
                  </div>
                  <span style={{ color: '#f59e0b', fontVariantNumeric: 'tabular-nums' }}>
                    {data.areas?.total
                      ? `${((100 * (data.areas.warning || 0)) / data.areas.total).toFixed(1)}%`
                      : '—'}
                    <span style={{ fontSize: '0.75rem', color: '#64748b' }}> · {data.warning_faces} faces</span>
                  </span>
                </div>
              </div>
            </div>

          </>
        )}
      </div>

      <div className="canvas-container">
        {loading && (
          <div className="loading-overlay">
            <div className="spinner"></div>
            <p style={{ fontWeight: 600, letterSpacing: '0.05em' }}>ANALYZING GEOMETRY</p>
          </div>
        )}
        {data?.geometry && (
          <ModelViewer geometry={data.geometry} />
        )}
        {!data && !loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', opacity: 0.5 }}>
            <Layers size={64} style={{ marginBottom: '1rem' }} />
            <h2>Waiting for 3D Model...</h2>
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
