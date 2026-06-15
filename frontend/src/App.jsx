import React, { useState, useRef } from 'react';
import axios from 'axios';
import { UploadCloud, CheckCircle, AlertCircle, Layers, ArrowUp, ArrowDown, ArrowRight, ArrowLeft } from 'lucide-react';
import ModelViewer from './ModelViewer';

function App() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const fileInputRef = useRef(null);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setSelectedFile(file);

    const formData = new FormData();
    formData.append('file', file);

    setLoading(true);
    setError(null);
    setData(null);

    try {
      const response = await axios.post('http://localhost:8000/analyze', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setData(response.data);
    } catch (err) {
      setError(err.message || 'Failed to analyze part.');
    } finally {
      setLoading(false);
    }
  };

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

  const handleDownloadReport = async () => {
    if (!selectedFile) return;
    const formData = new FormData();
    formData.append('file', selectedFile);
    try {
      const res = await axios.post('http://localhost:8000/report', formData, { responseType: 'blob' });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'DfM_Report.pdf');
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
    } catch (err) {
      setError("Failed to download PDF report");
    }
  };

  return (
    <div className="app-container">
      <div className="dashboard">
        <div className="dashboard-header">
          <h1>DfM Auto-Analyzer</h1>
          <p>AI-driven manufacturability checks</p>
        </div>

        {data ? (
          <div 
            onClick={() => fileInputRef.current.click()}
            style={{
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
            <input type="file" ref={fileInputRef} accept=".stp,.step" onChange={handleFileUpload} style={{display:'none'}} />
          </div>
        ) : (
          <div className="file-upload" onClick={() => fileInputRef.current.click()}>
            <UploadCloud color="var(--primary)" size={48} style={{ marginBottom: '1rem' }} />
            <h3>Upload CAD Part</h3>
            <p style={{ color: '#94a3b8', fontSize: '0.875rem', marginTop: '0.5rem' }}>
              Drag & drop or click to upload a .stp file
            </p>
            <input type="file" ref={fileInputRef} accept=".stp,.step" onChange={handleFileUpload} style={{display:'none'}} />
          </div>
        )}

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
                  Max area without undercuts
                </div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Undercuts</div>
                <div className="metric-value" style={{ color: data.undercut_faces > 0 ? '#ef4444' : '#10b981' }}>
                  {data.undercut_faces}
                </div>
                <div className="metric-subtext">
                  Faces trapped in mold
                </div>
              </div>
              <div className="metric-card" style={{ gridColumn: 'span 2' }}>
                <div className="metric-label">Parting Lines</div>
                <div className="metric-value" style={{ color: '#00ffff', fontSize: '1.25rem' }}>
                  {data.geometry?.parting_line_loops || 0} loops <span style={{fontSize: '0.875rem', color: '#94a3b8'}}>({data.geometry?.parting_lines?.length || 0} edges)</span>
                </div>
                <div className="metric-subtext">
                  Boundary edges splitting core & cavity
                </div>
              </div>
            </div>

            <div style={{ marginTop: '1rem' }}>
              <h3 style={{ fontSize: '1rem', marginBottom: '1rem', color: '#e2e8f0' }}>Face Classification</h3>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.875rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94a3b8' }}>Core Faces</span>
                  <span>{data.core_faces}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#94a3b8' }}>Cavity Faces</span>
                  <span>{data.cavity_faces}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', flexDirection: 'column' }}>
                    <span style={{ color: '#94a3b8' }}>Warning Faces</span>
                    <span style={{ fontSize: '10px', color: '#64748b' }}>(Draft angle &lt; 1°)</span>
                  </div>
                  <span style={{ color: '#f59e0b' }}>{data.warning_faces}</span>
                </div>
              </div>
            </div>

            <div style={{ marginTop: '1.5rem' }}>
              <button onClick={handleDownloadReport} style={{
                width: '100%',
                padding: '12px',
                background: 'linear-gradient(135deg, var(--primary), #2563eb)',
                color: 'white',
                border: 'none',
                borderRadius: '8px',
                fontWeight: 600,
                cursor: 'pointer',
                boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
              }}>
                📄 Download PDF Report
              </button>
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
