import React, { useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Environment, ContactShadows, Edges, Line, Bounds, Center } from '@react-three/drei';
import * as THREE from 'three';

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
    geometry.parting_lines.forEach((pts, idx) => {
      if (!pts || pts.length < 2) return;
      lines.push({ pts, id: `pl-${idx}` });
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

export default function ModelViewer({ geometry }) {
  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
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

        <OrbitControls makeDefault autoRotate autoRotateSpeed={1.5} />
      </Canvas>
      
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
