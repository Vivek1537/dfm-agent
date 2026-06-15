import React, { useMemo, useRef, useCallback } from 'react';
import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls, Environment, ContactShadows, Edges, Line, Bounds, Center } from '@react-three/drei';
import * as THREE from 'three';

class CanvasErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("3D Canvas error caught:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          position: 'absolute',
          inset: '1.5rem',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(30, 41, 59, 0.8)',
          backdropFilter: 'blur(12px)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: '12px',
          color: '#f8fafc',
          padding: '2rem',
          textAlign: 'center',
          boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.37)'
        }}>
          <h3 style={{ margin: '0 0 0.5rem 0', fontWeight: 600, color: '#ef4444', fontSize: '1.25rem' }}>3D Rendering Error</h3>
          <p style={{ margin: '0 0 1.5rem 0', opacity: 0.8, maxWidth: '400px', fontSize: '0.875rem' }}>
            {this.state.error?.message || "An error occurred while compiling the 3D scene."}
          </p>
          <button 
            onClick={() => this.setState({ hasError: false, error: null })}
            style={{
              padding: '8px 20px',
              background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              cursor: 'pointer',
              fontWeight: 600,
              boxShadow: '0 4px 12px rgba(37, 99, 235, 0.3)',
              transition: 'all 0.2s'
            }}
          >
            Retry Render
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

function MeshBuilder({ geometry }) {
  const meshes = useMemo(() => {
    const createdMeshes = [];

    geometry.faces.forEach((faceData, idx) => {
      const { vertices, triangles, classification } = faceData;
      
      if (!vertices || !triangles || vertices.length === 0 || triangles.length === 0) return;

      const posArray = new Float32Array(vertices.flat());
      const indexArray = new Uint32Array(triangles.flat());

      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
      geo.setIndex(new THREE.BufferAttribute(indexArray, 1));
      geo.computeVertexNormals();

      createdMeshes.push({ geo, classification, id: `face-${idx}` });
    });

    return createdMeshes;
  }, [geometry]);

  const partingLines = useMemo(() => {
    const lines = [];
    if (!geometry || !geometry.parting_lines) return lines;
    
    geometry.parting_lines.forEach((item, idx) => {
      if (!item) return;
      if (item.segments) {
        // V3 structured format: { loop_id, segments: [[...], [...]] }
        item.segments.forEach((seg, segIdx) => {
          if (!seg || seg.length < 2) return;
          lines.push({ pts: seg, id: `pl-${idx}-${segIdx}` });
        });
      } else if (Array.isArray(item)) {
        // V1 flat format: [[...], [...]]
        if (item.length < 2) return;
        lines.push({ pts: item, id: `pl-${idx}` });
      }
    });
    return lines;
  }, [geometry]);

  return (
    <group>
      {meshes.map(({ geo, classification, id }) => {
        let material;
        if (classification === 'undercut') {
          material = new THREE.MeshStandardMaterial({
            color: 0xff0000,
            emissive: 0xff0000,
            emissiveIntensity: 0.5,
            roughness: 0.2,
            metalness: 0.2
          });
        } else {
          material = new THREE.MeshStandardMaterial({
            color: 0x94a3b8,
            roughness: 0.5,
            metalness: 0.1,
            transparent: true,
            opacity: 0.85
          });
        }

        return (
          <mesh key={id} geometry={geo} material={material}>
            {classification !== 'undercut' && (
              <Edges scale={1} threshold={15} color="#1e293b" />
            )}
          </mesh>
        );
      })}

      {partingLines.map(({ pts, id }) => (
        <Line 
          key={id} 
          points={pts} 
          color="#00ffff" 
          lineWidth={5} 
          transparent 
          opacity={1} 
          depthTest={false}
        />
      ))}
    </group>
  );
}

// Camera controller that exposes a method to snap to preset views
function CameraController({ controlsRef }) {
  const { camera } = useThree();
  
  // Store camera ref for external use
  React.useEffect(() => {
    if (controlsRef) {
      controlsRef.current = { camera };
    }
  }, [camera, controlsRef]);

  return (
    <OrbitControls 
      makeDefault 
      enableDamping 
      dampingFactor={0.1} 
      rotateSpeed={0.8}
      zoomSpeed={1.2}
      panSpeed={0.8}
    />
  );
}

const VIEW_PRESETS = [
  { label: 'Front', icon: '▣', pos: [0, 0, 50] },
  { label: 'Back', icon: '▣', pos: [0, 0, -50] },
  { label: 'Top', icon: '⬆', pos: [0, 50, 0.01] },
  { label: 'Bottom', icon: '⬇', pos: [0, -50, 0.01] },
  { label: 'Left', icon: '◀', pos: [-50, 0, 0] },
  { label: 'Right', icon: '▶', pos: [50, 0, 0] },
  { label: 'ISO', icon: '◇', pos: [35, 25, 35] },
];

export default function ModelViewer({ geometry }) {
  const cameraRef = useRef(null);

  const handleViewClick = useCallback((pos) => {
    if (!cameraRef.current) return;
    const { camera } = cameraRef.current;
    camera.position.set(pos[0], pos[1], pos[2]);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
  }, []);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <CanvasErrorBoundary>
        <Canvas camera={{ position: [0, 0, 50], fov: 45 }}>
          <color attach="background" args={['transparent']} />
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 10, 10]} intensity={1} />
          <directionalLight position={[-10, -10, -10]} intensity={0.5} />
          
          <Center>
            <Bounds fit clip observe margin={1.2}>
              <MeshBuilder geometry={geometry} />
            </Bounds>
          </Center>
          <ContactShadows position={[0, -10, 0]} opacity={0.5} scale={100} blur={2} far={20} />

          <CameraController controlsRef={cameraRef} />
        </Canvas>
      </CanvasErrorBoundary>

      {/* View Navigation Panel */}
      <div className="view-nav-panel">
        {VIEW_PRESETS.map(({ label, icon, pos }) => (
          <button
            key={label}
            className="view-nav-btn"
            title={label}
            onClick={() => handleViewClick(pos)}
          >
            <span className="view-nav-icon">{icon}</span>
            <span className="view-nav-label">{label}</span>
          </button>
        ))}
      </div>
      
      <div className="legend-overlay">
        <div className="legend-item">
          <span className="legend-color" style={{background: '#ff0000', boxShadow: '0 0 8px rgba(255,0,0,0.8)'}}></span>
          Undercuts
        </div>
        <div className="legend-item">
          <span className="legend-color" style={{background: '#94a3b8'}}></span>
          Core/Cavity
        </div>
        <div className="legend-item">
          <span className="legend-line"></span>
          Parting Line
        </div>
      </div>
    </div>
  );
}

