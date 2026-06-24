import React, { useMemo, useRef, useCallback, useState, useEffect } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls, Edges, Billboard, Text, Line } from '@react-three/drei';
import { Layers, ArrowDown, ArrowUp, Grid3X3 } from 'lucide-react';
import * as THREE from 'three';

// Optional Drei version reminder comment:
// No drei version bump required; using standard Text, Billboard, and OrbitControls.

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
          boxShadow: '0 8px 32px 0 rgba(0, 0, 0, 0.37)',
          zIndex: 99
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

// ── REFERENCE PLANES HELPERS ───────────────────────────────────────────

function PlaneEdges({ width, height, color }) {
  const points = useMemo(() => {
    const halfW = width / 2;
    const halfH = height / 2;
    return [
      new THREE.Vector3(-halfW, -halfH, 0),
      new THREE.Vector3(halfW, -halfH, 0),
      new THREE.Vector3(halfW, halfH, 0),
      new THREE.Vector3(-halfW, halfH, 0),
      new THREE.Vector3(-halfW, -halfH, 0),
    ];
  }, [width, height]);

  const geo = useMemo(() => {
    return new THREE.BufferGeometry().setFromPoints(points);
  }, [points]);

  return (
    <line geometry={geo}>
      <lineBasicMaterial color={color} depthWrite={false} transparent opacity={0.8} />
    </line>
  );
}

function PlaneGrid({ width, height, color, opacity }) {
  const minorStep = 2;
  const majorStep = 10;
  
  const { minorPoints, majorPoints } = useMemo(() => {
    const minor = [];
    const major = [];
    const halfW = width / 2;
    const halfH = height / 2;

    const startX = Math.ceil(-halfW / minorStep) * minorStep;
    const endX = Math.floor(halfW / minorStep) * minorStep;
    for (let x = startX; x <= endX; x = parseFloat((x + minorStep).toFixed(4))) {
      const isMajor = Math.abs(x % majorStep) < 0.001 || Math.abs((x % majorStep) - majorStep) < 0.001;
      const target = isMajor ? major : minor;
      target.push(new THREE.Vector3(x, -halfH, 0), new THREE.Vector3(x, halfH, 0));
    }

    const startY = Math.ceil(-halfH / minorStep) * minorStep;
    const endY = Math.floor(halfH / minorStep) * minorStep;
    for (let y = startY; y <= endY; y = parseFloat((y + minorStep).toFixed(4))) {
      const isMajor = Math.abs(y % majorStep) < 0.001 || Math.abs((y % majorStep) - majorStep) < 0.001;
      const target = isMajor ? major : minor;
      target.push(new THREE.Vector3(-halfW, y, 0), new THREE.Vector3(halfW, y, 0));
    }

    return { minorPoints: minor, majorPoints: major };
  }, [width, height]);

  const minorGeo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    if (minorPoints.length > 0) g.setFromPoints(minorPoints);
    return g;
  }, [minorPoints]);

  const majorGeo = useMemo(() => {
    const g = new THREE.BufferGeometry();
    if (majorPoints.length > 0) g.setFromPoints(majorPoints);
    return g;
  }, [majorPoints]);

  return (
    <group>
      {minorPoints.length > 0 && (
        <lineSegments geometry={minorGeo}>
          <lineBasicMaterial color={color} transparent opacity={opacity * 0.4} depthWrite={false} />
        </lineSegments>
      )}
      {majorPoints.length > 0 && (
        <lineSegments geometry={majorGeo}>
          <lineBasicMaterial color={color} transparent opacity={opacity} depthWrite={false} />
        </lineSegments>
      )}
    </group>
  );
}

function ReferencePlane({ width, height, normal, color, opacity = 0.10, edgeColor, gridColor = '#6B7280' }) {
  const rotation = useMemo(() => {
    if (normal[0] !== 0) return [0, Math.PI / 2, 0]; // YZ plane (normal along X)
    if (normal[1] !== 0) return [-Math.PI / 2, 0, 0]; // XZ plane (normal along Y)
    return [0, 0, 0]; // XY plane (normal along Z)
  }, [normal]);

  return (
    <group rotation={rotation}>
      <mesh>
        <planeGeometry args={[width, height]} />
        <meshBasicMaterial 
          color="#FFFFFF" 
          transparent 
          opacity={opacity} 
          side={THREE.DoubleSide} 
          depthWrite={false}
        />
      </mesh>
      <PlaneEdges width={width} height={height} color={edgeColor} />
      <PlaneGrid width={width} height={height} color={gridColor} opacity={0.25} />
    </group>
  );
}

function AxisSystem({ bboxInfo }) {
  const arrowLength = bboxInfo.diagonal * 0.35;
  const headLength = arrowLength * 0.2;
  const headWidth = arrowLength * 0.1;
  const labelSize = bboxInfo.diagonal * 0.035;

  const arrowX = useMemo(() => new THREE.ArrowHelper(new THREE.Vector3(1, 0, 0), new THREE.Vector3(0, 0, 0), arrowLength, 0xEF4444, headLength, headWidth), [arrowLength, headLength, headWidth]);
  const arrowY = useMemo(() => new THREE.ArrowHelper(new THREE.Vector3(0, 1, 0), new THREE.Vector3(0, 0, 0), arrowLength, 0x10B981, headLength, headWidth), [arrowLength, headLength, headWidth]);
  const arrowZ = useMemo(() => new THREE.ArrowHelper(new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, 0), arrowLength, 0x3B82F6, headLength, headWidth), [arrowLength, headLength, headWidth]);

  return (
    <group>
      <primitive object={arrowX} />
      <primitive object={arrowY} />
      <primitive object={arrowZ} />

      <Billboard position={[arrowLength + headLength * 1.3, 0, 0]}>
        <Text color="#EF4444" fontSize={labelSize} anchorX="center" anchorY="middle">X</Text>
      </Billboard>
      <Billboard position={[0, arrowLength + headLength * 1.3, 0]}>
        <Text color="#10B981" fontSize={labelSize} anchorX="center" anchorY="middle">Y</Text>
      </Billboard>
      <Billboard position={[0, 0, arrowLength + headLength * 1.3]}>
        <Text color="#3B82F6" fontSize={labelSize} anchorX="center" anchorY="middle">Z</Text>
      </Billboard>
    </group>
  );
}

// ── DASHED EDGES COMPONENT FOR 3D REGIONS ────────────────────────────────
// (kept for potential reuse but no longer used inside MeshBuilder)
function DashedEdges({ geometry, color }) {
  const lineRef = useRef();

  const edgesGeo = useMemo(() => {
    return new THREE.EdgesGeometry(geometry, 25);
  }, [geometry]);

  useEffect(() => {
    if (lineRef.current) {
      lineRef.current.computeLineDistances();
    }
  }, [edgesGeo]);

  return (
    <lineSegments ref={lineRef} geometry={edgesGeo} renderOrder={950}>
      <lineDashedMaterial
        color={color}
        dashSize={1.2}
        gapSize={0.6}
        linewidth={2}
        depthTest={false}
        transparent
      />
    </lineSegments>
  );
}

// ── MESH BUILDER WITH EXPLODED VIEW ─────────────────────────────────────
// Core and cavity face groups animate apart along the mold pull direction
// when their respective toggle is active. Undercut faces stay at origin.

function MeshBuilder({ geometry, bboxInfo, moldDirection, showCore, showCavity }) {
  const coreGroupRef = useRef();
  const cavityGroupRef = useRef();

  const moldDir = useMemo(() => {
    const d = new THREE.Vector3(...moldDirection);
    return d.lengthSq() > 0.0001 ? d.normalize() : new THREE.Vector3(0, 0, 1);
  }, [moldDirection]);

  const explodeDistance = bboxInfo.diagonal * 0.3;

  // Smooth lerp animation — no allocations per frame
  useFrame(() => {
    if (coreGroupRef.current) {
      const t = showCore ? -explodeDistance : 0;
      const p = coreGroupRef.current.position;
      p.x += (moldDir.x * t - p.x) * 0.08;
      p.y += (moldDir.y * t - p.y) * 0.08;
      p.z += (moldDir.z * t - p.z) * 0.08;
    }
    if (cavityGroupRef.current) {
      const t = showCavity ? explodeDistance : 0;
      const p = cavityGroupRef.current.position;
      p.x += (moldDir.x * t - p.x) * 0.08;
      p.y += (moldDir.y * t - p.y) * 0.08;
      p.z += (moldDir.z * t - p.z) * 0.08;
    }
  });

  // Build and categorize meshes
  const { coreMeshes, cavityMeshes, otherMeshes, coreCentroid, cavityCentroid } = useMemo(() => {
    const core = [], cavity = [], other = [];
    const corePosSum = new THREE.Vector3();
    const cavityPosSum = new THREE.Vector3();
    let coreVerts = 0, cavityVerts = 0;

    if (!geometry) return { coreMeshes: core, cavityMeshes: cavity, otherMeshes: other, coreCentroid: [0,0,0], cavityCentroid: [0,0,0] };

    const addVertex = (v, cls) => {
      if (cls === 'core') { corePosSum.x += v[0]; corePosSum.y += v[1]; corePosSum.z += v[2]; coreVerts++; }
      else if (cls === 'cavity') { cavityPosSum.x += v[0]; cavityPosSum.y += v[1]; cavityPosSum.z += v[2]; cavityVerts++; }
    };

    if (Array.isArray(geometry.faces)) {
      geometry.faces.forEach((faceData, idx) => {
        const { vertices, triangles, classification } = faceData;
        if (!vertices || !triangles || vertices.length === 0 || triangles.length === 0) return;

        const translated = vertices.map(v => [
          v[0] - bboxInfo.center.x,
          v[1] - bboxInfo.center.y,
          v[2] - bboxInfo.center.z
        ]);

        const posArray = new Float32Array(translated.flat());
        const indexArray = new Uint32Array(triangles.flat());
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
        geo.setIndex(new THREE.BufferAttribute(indexArray, 1));
        geo.computeVertexNormals();

        const entry = { geo, classification, id: `face-${idx}` };
        // Swap mapping: backend 'cavity' (dot>=0, normals WITH pull) → frontend CORE group
        //               backend 'core'   (dot<0,  normals AGAINST pull) → frontend CAVITY group
        if (classification === 'cavity') { core.push(entry); translated.forEach(v => addVertex(v, 'core')); }
        else if (classification === 'core') { cavity.push(entry); translated.forEach(v => addVertex(v, 'cavity')); }
        else { other.push(entry); }
      });
    } else if (geometry.vertices && geometry.faces) {
      const numTri = geometry.faces.length / 3;
      for (let i = 0; i < numTri; i++) {
        const i0 = geometry.faces[i*3], i1 = geometry.faces[i*3+1], i2 = geometry.faces[i*3+2];
        const cls = (geometry.faceStatus && geometry.faceStatus[i]) || 'cavity';
        const cx = bboxInfo.center.x, cy = bboxInfo.center.y, cz = bboxInfo.center.z;

        const p0 = [geometry.vertices[i0*3]-cx, geometry.vertices[i0*3+1]-cy, geometry.vertices[i0*3+2]-cz];
        const p1 = [geometry.vertices[i1*3]-cx, geometry.vertices[i1*3+1]-cy, geometry.vertices[i1*3+2]-cz];
        const p2 = [geometry.vertices[i2*3]-cx, geometry.vertices[i2*3+1]-cy, geometry.vertices[i2*3+2]-cz];

        const posArray = new Float32Array([...p0, ...p1, ...p2]);
        const geo = new THREE.BufferGeometry();
        geo.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
        geo.computeVertexNormals();

        const entry = { geo, classification: cls, id: `face-${i}` };
        // Same swap as above
        if (cls === 'cavity') { core.push(entry); [p0,p1,p2].forEach(v => addVertex(v, 'core')); }
        else if (cls === 'core') { cavity.push(entry); [p0,p1,p2].forEach(v => addVertex(v, 'cavity')); }
        else { other.push(entry); }
      }
    }

    const cc = coreVerts > 0 ? [corePosSum.x/coreVerts, corePosSum.y/coreVerts, corePosSum.z/coreVerts] : [0,0,0];
    const cvc = cavityVerts > 0 ? [cavityPosSum.x/cavityVerts, cavityPosSum.y/cavityVerts, cavityPosSum.z/cavityVerts] : [0,0,0];

    return { coreMeshes: core, cavityMeshes: cavity, otherMeshes: other, coreCentroid: cc, cavityCentroid: cvc };
  }, [geometry, bboxInfo]);

  // Shared materials (stable references)
  const greyMat = useMemo(() => new THREE.MeshStandardMaterial({
    color: 0x94a3b8, roughness: 0.5, metalness: 0.1, transparent: true, opacity: 0.85
  }), []);
  const undercutMat = useMemo(() => new THREE.MeshStandardMaterial({
    color: 0xef4444, emissive: 0xef4444, emissiveIntensity: 0.4, roughness: 0.3, metalness: 0.1
  }), []);

  const labelSize = bboxInfo.diagonal * 0.04;

  return (
    <group>
      {/* ── Core faces ── */}
      <group ref={coreGroupRef}>
        {coreMeshes.map(({ geo, id }) => (
          <mesh key={id} geometry={geo} material={greyMat}>
            <Edges scale={1} threshold={25} color="#000000" transparent opacity={0.4} />
            {showCore && <DashedEdges geometry={geo} color="#1D4ED8" />}
          </mesh>
        ))}
        {showCore && coreMeshes.length > 0 && (
          <Billboard position={coreCentroid}>
            <mesh renderOrder={910}>
              <planeGeometry args={[labelSize * 3.2, labelSize * 1.5]} />
              <meshBasicMaterial color="#ECEEF1" depthTest={false} transparent opacity={0.92} />
            </mesh>
            <Text color="#1D4ED8" fontSize={labelSize} fontWeight={700}
              anchorX="center" anchorY="middle" depthTest={false}
              position={[0, 0, 0.01]} renderOrder={911}
            >CORE</Text>
          </Billboard>
        )}
      </group>

      {/* ── Cavity faces ── */}
      <group ref={cavityGroupRef}>
        {cavityMeshes.map(({ geo, id }) => (
          <mesh key={id} geometry={geo} material={greyMat}>
            <Edges scale={1} threshold={25} color="#000000" transparent opacity={0.4} />
            {showCavity && <DashedEdges geometry={geo} color="#15803D" />}
          </mesh>
        ))}
        {showCavity && cavityMeshes.length > 0 && (
          <Billboard position={cavityCentroid}>
            <mesh renderOrder={910}>
              <planeGeometry args={[labelSize * 4.2, labelSize * 1.5]} />
              <meshBasicMaterial color="#ECEEF1" depthTest={false} transparent opacity={0.92} />
            </mesh>
            <Text color="#15803D" fontSize={labelSize} fontWeight={700}
              anchorX="center" anchorY="middle" depthTest={false}
              position={[0, 0, 0.01]} renderOrder={911}
            >CAVITY</Text>
          </Billboard>
        )}
      </group>

      {/* ── Other faces (undercut, warning) stay at origin ── */}
      {otherMeshes.map(({ geo, classification, id }) => {
        let mat = greyMat;
        if (classification === 'undercut') mat = undercutMat;
        return (
          <mesh key={id} geometry={geo} material={mat}>
            <Edges scale={1} threshold={25} color="#000000" transparent opacity={0.4} />
          </mesh>
        );
      })}
    </group>
  );
}

// ── PARTING LINE RENDERER ─────────────────────────────────────────────────
// Each segment from the API is an independent list of sampled edge points.
// We render every segment as its own <Line> so they precisely hug the part
// boundary without any spurious cross-part connectors.

function PartingLines({ geometry, bboxInfo }) {
  const segments = useMemo(() => {
    const result = [];
    if (!geometry || !geometry.parting_lines) return result;

    geometry.parting_lines.forEach((item, loopIdx) => {
      if (!item) return;

      // Each parting_lines entry has a `segments` array.
      // Each segment is already a list of [x,y,z] points along one CAD edge.
      // Render each segment independently — never stitch across segment boundaries.
      if (item.segments && Array.isArray(item.segments)) {
        item.segments.forEach((seg, segIdx) => {
          if (!seg || seg.length < 2) return;
          const pts = seg.map(p => [
            p[0] - bboxInfo.center.x,
            p[1] - bboxInfo.center.y,
            p[2] - bboxInfo.center.z
          ]);
          result.push({ points: pts, id: `pl-${loopIdx}-${segIdx}` });
        });
      } else if (item.points && Array.isArray(item.points)) {
        // Fallback: flat points array
        if (item.points.length < 2) return;
        const pts = item.points.map(p => [
          p[0] - bboxInfo.center.x,
          p[1] - bboxInfo.center.y,
          p[2] - bboxInfo.center.z
        ]);
        result.push({ points: pts, id: `pl-${loopIdx}-0` });
      } else if (Array.isArray(item)) {
        if (item.length < 2) return;
        const pts = item.map(p => [
          p[0] - bboxInfo.center.x,
          p[1] - bboxInfo.center.y,
          p[2] - bboxInfo.center.z
        ]);
        result.push({ points: pts, id: `pl-${loopIdx}-0` });
      }
    });

    return result;
  }, [geometry, bboxInfo]);

  return (
    <group>
      {segments.map(({ points, id }) => (
        <Line
          key={id}
          points={points}
          color="#3B82F6"
          lineWidth={3}
          transparent
          opacity={1}
          depthTest={false}
          renderOrder={999}
        />
      ))}
    </group>
  );
}

// ── CONVEX HULL ALGORITHM ──────────────────────────────────────────────

function crossProduct(a, b, c) {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

function getConvexHull2D(points) {
  if (points.length <= 1) return points;

  const sorted = [...points].sort((a, b) => a.x !== b.x ? a.x - b.x : a.y - b.y);

  const lower = [];
  for (let i = 0; i < sorted.length; i++) {
    while (lower.length >= 2 && crossProduct(lower[lower.length - 2], lower[lower.length - 1], sorted[i]) <= 0) {
      lower.pop();
    }
    lower.push(sorted[i]);
  }

  const upper = [];
  for (let i = sorted.length - 1; i >= 0; i--) {
    while (upper.length >= 2 && crossProduct(upper[upper.length - 2], upper[upper.length - 1], sorted[i]) <= 0) {
      upper.pop();
    }
    upper.push(sorted[i]);
  }

  lower.pop();
  upper.pop();

  return lower.concat(upper);
}

// ── CORE/CAVITY REGION ANNOTATIONS ────────────────────────────────────

function RegionAnnotations({ geometry, bboxInfo, moldDirection, showCore, showCavity }) {
  const lineRefCavity = useRef();
  const lineRefCore = useRef();

  const N = useMemo(() => {
    let dir = new THREE.Vector3(...moldDirection);
    if (dir.lengthSq() < 0.0001) {
      dir.set(0, 0, 1);
    }
    return dir.normalize();
  }, [moldDirection]);

  // Quaternion to rotate from standard XY plane (Z-normal) to moldDirection normal plane
  const quaternion = useMemo(() => {
    return new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), N);
  }, [N]);

  const annotations = useMemo(() => {
    const processRegion = (targetClass) => {
      let regionFaces = [];
      if (Array.isArray(geometry?.faces)) {
        regionFaces = geometry.faces.filter(f => f.classification === targetClass);
      } else if (geometry?.vertices && geometry?.faces && geometry?.faceStatus) {
        const numTriangles = geometry.faces.length / 3;
        for (let i = 0; i < numTriangles; i++) {
          if (geometry.faceStatus[i] === targetClass) {
            regionFaces.push({
              vertices: [
                [geometry.vertices[geometry.faces[i*3]*3], geometry.vertices[geometry.faces[i*3]*3+1], geometry.vertices[geometry.faces[i*3]*3+2]],
                [geometry.vertices[geometry.faces[i*3+1]*3], geometry.vertices[geometry.faces[i*3+1]*3+1], geometry.vertices[geometry.faces[i*3+1]*3+2]],
                [geometry.vertices[geometry.faces[i*3+2]*3], geometry.vertices[geometry.faces[i*3+2]*3+1], geometry.vertices[geometry.faces[i*3+2]*3+2]]
              ]
            });
          }
        }
      }

      if (regionFaces.length === 0) return null;

      // Project unique vertices onto 2D local XY plane of the oriented boundary
      const invQuat = quaternion.clone().invert();
      const localPts = [];
      const seen = new Set();

      regionFaces.forEach(face => {
        if (!face.vertices) return;
        face.vertices.forEach(v => {
          const key = `${v[0].toFixed(2)}_${v[1].toFixed(2)}_${v[2].toFixed(2)}`;
          if (!seen.has(key)) {
            seen.add(key);
            const v3 = new THREE.Vector3(v[0] - bboxInfo.center.x, v[1] - bboxInfo.center.y, v[2] - bboxInfo.center.z);
            const localV = v3.applyQuaternion(invQuat);
            localPts.push({ x: localV.x, y: localV.y });
          }
        });
      });

      if (localPts.length === 0) return null;

      // Calculate Convex Hull boundary in 2D
      const hull2D = getConvexHull2D(localPts);
      if (hull2D.length < 3) return null;

      // Centroid of the hull
      let sumX = 0, sumY = 0;
      hull2D.forEach(p => {
        sumX += p.x;
        sumY += p.y;
      });
      const centroidX = sumX / hull2D.length;
      const centroidY = sumY / hull2D.length;

      // Offset along the local Z normal axis (separated vertically along pull direction).
      // Mold convention: CAVITY is the half facing the pull direction (+localZ).
      // CORE is the half facing against the pull direction (-localZ).
      const separateDist = bboxInfo.size.z * 0.45 + bboxInfo.diagonal * 0.04;
      // cavity = top half (positive pull direction), core = bottom half (negative pull direction)
      const localZ = targetClass === 'cavity' ? separateDist : -separateDist;

      // Expand outward by 12% of bbox diagonal
      const displacement = 0.12 * bboxInfo.diagonal;
      const expandedPts = hull2D.map(p => {
        const dx = p.x - centroidX;
        const dy = p.y - centroidY;
        const len = Math.hypot(dx, dy);
        if (len > 0.0001) {
          return new THREE.Vector3(
            p.x + (dx / len) * displacement,
            p.y + (dy / len) * displacement,
            localZ
          );
        }
        return new THREE.Vector3(p.x, p.y, localZ);
      });

      // Create closed loop for LineDashedMaterial
      const linePts = [...expandedPts, expandedPts[0]];
      const outlineGeo = new THREE.BufferGeometry().setFromPoints(linePts);

      // Find topmost point of expandedPts along local Y axis (up vector of the parting plane)
      let topPt = expandedPts[0];
      for (let i = 1; i < expandedPts.length; i++) {
        if (expandedPts[i].y > topPt.y) {
          topPt = expandedPts[i];
        }
      }

      // Outward boundary normal at the top point
      const dx = topPt.x - centroidX;
      const dy = topPt.y - centroidY;
      const len = Math.hypot(dx, dy);
      const dir = new THREE.Vector3(
        len > 0.0001 ? dx / len : 0,
        len > 0.0001 ? dy / len : 1,
        0
      );

      // Offset label outward along the normal
      const labelOffsetDist = bboxInfo.diagonal * 0.04;
      const labelPos = new THREE.Vector3(
        topPt.x + dir.x * labelOffsetDist,
        topPt.y + dir.y * labelOffsetDist,
        localZ + (targetClass === 'cavity' ? 0.05 : -0.05)
      );

      const labelSize = bboxInfo.diagonal * 0.04;
      const pillWidth = labelSize * (targetClass === 'cavity' ? 3.5 : 2.5);
      const pillHeight = labelSize * 1.3;

      return {
        outlineGeo,
        labelPos,
        pillWidth,
        pillHeight
      };
    };

    return {
      cavity: processRegion('cavity'),
      core: processRegion('core')
    };
  }, [geometry, bboxInfo, quaternion, N]);

  // computeLineDistances on line refs once updated
  useEffect(() => {
    if (annotations.cavity?.outlineGeo && lineRefCavity.current) {
      lineRefCavity.current.computeLineDistances();
    }
  }, [annotations.cavity]);

  useEffect(() => {
    if (annotations.core?.outlineGeo && lineRefCore.current) {
      lineRefCore.current.computeLineDistances();
    }
  }, [annotations.core]);

  const labelSize = bboxInfo.diagonal * 0.04;

  return (
    <group quaternion={quaternion}>
      {/* CAVITY SILHOUETTE */}
      {showCavity && annotations.cavity && (
        <group>
          {/* Dashed outer silhouette loop in deep green */}
          <lineSegments ref={lineRefCavity} geometry={annotations.cavity.outlineGeo} renderOrder={900}>
            <lineDashedMaterial
              color="#15803D"
              dashSize={1.2}
              gapSize={0.6}
              linewidth={2}
              depthTest={false}
              transparent
            />
          </lineSegments>

          {/* Label with background pill and color matched text */}
          <Billboard 
            position={annotations.cavity.labelPos} 
            renderOrder={900}
          >
            <mesh>
              <planeGeometry args={[annotations.cavity.pillWidth, annotations.cavity.pillHeight]} />
              <meshBasicMaterial color="#ECEEF1" depthTest={false} />
            </mesh>
            <Text
              color="#15803D"
              fontSize={labelSize}
              fontWeight={700}
              anchorX="center"
              anchorY="middle"
              depthTest={false}
              position={[0, 0, 0.01]}
            >
              CAVITY
            </Text>
          </Billboard>
        </group>
      )}

      {/* CORE SILHOUETTE */}
      {showCore && annotations.core && (
        <group>
          {/* Dashed outer silhouette loop in deep blue */}
          <lineSegments ref={lineRefCore} geometry={annotations.core.outlineGeo} renderOrder={900}>
            <lineDashedMaterial
              color="#1D4ED8"
              dashSize={1.2}
              gapSize={0.6}
              linewidth={2}
              depthTest={false}
              transparent
            />
          </lineSegments>

          {/* Label with background pill and color matched text */}
          <Billboard 
            position={annotations.core.labelPos} 
            renderOrder={900}
          >
            <mesh>
              <planeGeometry args={[annotations.core.pillWidth, annotations.core.pillHeight]} />
              <meshBasicMaterial color="#ECEEF1" depthTest={false} />
            </mesh>
            <Text
              color="#1D4ED8"
              fontSize={labelSize}
              fontWeight={700}
              anchorX="center"
              anchorY="middle"
              depthTest={false}
              position={[0, 0, 0.01]}
            >
              CORE
            </Text>
          </Billboard>
        </group>
      )}
    </group>
  );
}

// ── CAMERA SYNCHRONIZATION HELPERS ────────────────────────────────────

function CameraSync({ cameraRef, controlsRef }) {
  const { camera } = useThree();
  useEffect(() => {
    if (cameraRef) {
      cameraRef.current = camera;
    }
  }, [camera, cameraRef]);
  return null;
}

// ── MAIN EXPORT COMPONENT ──────────────────────────────────────────────

export default function ModelViewer({ geometry }) {
  const cameraRef = useRef(null);
  const controlsRef = useRef(null);

  // Core and Cavity toggles (default to false)
  const [showCore, setShowCore] = useState(false);
  const [showCavity, setShowCavity] = useState(false);
  const [showPlanes, setShowPlanes] = useState(true);

  // Both toggle button behavior
  const handleBothClick = () => {
    if (showCore && showCavity) {
      setShowCore(false);
      setShowCavity(false);
    } else {
      setShowCore(true);
      setShowCavity(true);
    }
  };

  // Compute Bounding Box information once
  const bboxInfo = useMemo(() => {
    let minX = Infinity, minY = Infinity, minZ = Infinity;
    let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
    let hasVertices = false;

    if (Array.isArray(geometry?.faces)) {
      geometry.faces.forEach(face => {
        if (!face.vertices) return;
        face.vertices.forEach(v => {
          if (v && v.length >= 3) {
            const [x, y, z] = v;
            if (x < minX) minX = x;
            if (y < minY) minY = y;
            if (z < minZ) minZ = z;
            if (x > maxX) maxX = x;
            if (y > maxY) maxY = y;
            if (z > maxZ) maxZ = z;
            hasVertices = true;
          }
        });
      });
    } else if (geometry?.vertices) {
      const v = geometry.vertices;
      for (let i = 0; i < v.length; i += 3) {
        const x = v[i], y = v[i+1], z = v[i+2];
        if (x < minX) minX = x;
        if (y < minY) minY = y;
        if (z < minZ) minZ = z;
        if (x > maxX) maxX = x;
        if (y > maxY) maxY = y;
        if (z > maxZ) maxZ = z;
        hasVertices = true;
      }
    }

    if (!hasVertices) {
      return {
        center: new THREE.Vector3(0, 0, 0),
        size: new THREE.Vector3(10, 10, 10),
        diagonal: 17.32,
        min: new THREE.Vector3(-5, -5, -5),
        max: new THREE.Vector3(5, 5, 5)
      };
    }

    const min = new THREE.Vector3(minX, minY, minZ);
    const max = new THREE.Vector3(maxX, maxY, maxZ);
    const center = new THREE.Vector3().addVectors(min, max).multiplyScalar(0.5);
    const size = new THREE.Vector3().subVectors(max, min);
    const diagonal = min.distanceTo(max);

    return { center, size, diagonal, min, max };
  }, [geometry]);

  // Extract Mold Pull Direction
  const moldDirection = useMemo(() => {
    let dir = [0, 0, 1];
    if (geometry?.moldDirection) dir = geometry.moldDirection;
    else if (geometry?.best_direction) dir = geometry.best_direction;

    const len = Math.sqrt(dir[0]*dir[0] + dir[1]*dir[1] + dir[2]*dir[2]);
    if (len > 0.0001) {
      return [dir[0]/len, dir[1]/len, dir[2]/len];
    }
    return [0, 0, 1];
  }, [geometry]);

  // Auto-fit camera and controls when geometry changes
  useEffect(() => {
    if (cameraRef.current) {
      const dist = bboxInfo.diagonal * 2.5;
      const isoDist = dist / Math.sqrt(3);
      cameraRef.current.position.set(isoDist, isoDist, isoDist);
      cameraRef.current.lookAt(0, 0, 0);
      cameraRef.current.updateProjectionMatrix();
      if (controlsRef.current) {
        controlsRef.current.target.set(0, 0, 0);
        controlsRef.current.update();
      }
    }
  }, [bboxInfo]);

  // View Preset Button click handlers
  const handleViewClick = useCallback((pos) => {
    if (!cameraRef.current) return;
    const camera = cameraRef.current;
    camera.position.set(pos[0], pos[1], pos[2]);
    camera.lookAt(0, 0, 0);
    camera.updateProjectionMatrix();
    if (controlsRef.current) {
      controlsRef.current.target.set(0, 0, 0);
      controlsRef.current.update();
    }
  }, []);

  const dist = bboxInfo.diagonal * 2.5;
  const isoDist = dist / Math.sqrt(3);
  const VIEW_PRESETS = [
    { label: 'Front', icon: '▣', pos: [0, 0, dist] },
    { label: 'Back', icon: '▣', pos: [0, 0, -dist] },
    { label: 'Top', icon: '⬆', pos: [0, dist, 0.001] },
    { label: 'Bottom', icon: '⬇', pos: [0, -dist, 0.001] },
    { label: 'Left', icon: '◀', pos: [-dist, 0, 0] },
    { label: 'Right', icon: '▶', pos: [dist, 0, 0] },
    { label: 'ISO', icon: '◇', pos: [isoDist, isoDist, isoDist] },
  ];

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      <CanvasErrorBoundary>
        <Canvas camera={{ position: [isoDist, isoDist, isoDist], fov: 45 }}>
          {/* Background and lighting */}
          <color attach="background" args={['#ECEEF1']} />
          <ambientLight intensity={0.55} />
          <directionalLight 
            position={[moldDirection[0] * 100, moldDirection[1] * 100, moldDirection[2] * 100]} 
            intensity={0.9} 
            castShadow={false}
          />
          
          {/* Reference Planes (Z-normal = XY, X-normal = YZ, Y-normal = XZ) */}
          {showPlanes && (
            <>
              <ReferencePlane 
                width={bboxInfo.size.x * 2.2} 
                height={bboxInfo.size.y * 2.2} 
                normal={[0, 0, 1]} 
                color="#FFFFFF" 
                edgeColor="#3B82F6" 
              />
              <ReferencePlane 
                width={bboxInfo.size.z * 2.2} 
                height={bboxInfo.size.y * 2.2} 
                normal={[1, 0, 0]} 
                color="#FFFFFF" 
                edgeColor="#EF4444" 
              />
              <ReferencePlane 
                width={bboxInfo.size.x * 2.2} 
                height={bboxInfo.size.z * 2.2} 
                normal={[0, 1, 0]} 
                color="#FFFFFF" 
                edgeColor="#10B981" 
              />
            </>
          )}

          {/* Reference Arrows — tied to planes toggle */}
          {showPlanes && <AxisSystem bboxInfo={bboxInfo} />}

          {/* CAD Mesh geometry with exploded view */}
          <MeshBuilder 
            geometry={geometry} 
            bboxInfo={bboxInfo}
            moldDirection={moldDirection}
            showCore={showCore}
            showCavity={showCavity}
          />

          {/* Parting Lines */}
          <PartingLines 
            geometry={geometry} 
            bboxInfo={bboxInfo} 
          />

          {/* Sync camera reference */}
          <CameraSync cameraRef={cameraRef} controlsRef={controlsRef} />

          {/* Controls */}
          <OrbitControls 
            ref={controlsRef}
            makeDefault 
            enableDamping 
            dampingFactor={0.1} 
            rotateSpeed={0.8}
            zoomSpeed={1.2}
            panSpeed={0.8}
          />
        </Canvas>
      </CanvasErrorBoundary>

      {/* Visibility Toggle Floating Panel */}
      <div style={{
        position: 'absolute',
        top: '1.5rem',
        right: '9rem',
        display: 'flex',
        gap: '8px',
        zIndex: 10,
      }}>
        {/* Planes Toggle */}
        <button
          onClick={() => setShowPlanes(prev => !prev)}
          title="Toggle Reference Planes"
          style={{
            width: '88px',
            height: '36px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            cursor: 'pointer',
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.825rem',
            fontWeight: 600,
            transition: 'all 0.2s',
            background: showPlanes ? '#6366F1' : '#ffffff',
            color: showPlanes ? '#ffffff' : '#111827',
            border: showPlanes ? 'none' : '1px solid #D1D5DB',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
          }}
        >
          <Grid3X3 size={14} /> Planes
        </button>
        {/* Both Button */}
        <button
          onClick={handleBothClick}
          title="Toggle Both Silhouettes"
          style={{
            width: '88px',
            height: '36px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            cursor: 'pointer',
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.825rem',
            fontWeight: 600,
            transition: 'all 0.2s',
            background: (showCore && showCavity) ? '#111827' : '#ffffff',
            color: (showCore && showCavity) ? '#ffffff' : '#111827',
            border: (showCore && showCavity) ? 'none' : '1px solid #D1D5DB',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
          }}
        >
          <Layers size={14} /> Both
        </button>

        {/* Core Button */}
        <button
          onClick={() => setShowCore(prev => !prev)}
          title="Toggle Core Silhouette"
          style={{
            width: '88px',
            height: '36px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            cursor: 'pointer',
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.825rem',
            fontWeight: 600,
            transition: 'all 0.2s',
            background: showCore ? '#1D4ED8' : '#ffffff',
            color: showCore ? '#ffffff' : '#111827',
            border: showCore ? 'none' : '1px solid #D1D5DB',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
          }}
        >
          <ArrowDown size={14} /> Core
        </button>

        {/* Cavity Button */}
        <button
          onClick={() => setShowCavity(prev => !prev)}
          title="Toggle Cavity Silhouette"
          style={{
            width: '88px',
            height: '36px',
            borderRadius: '6px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            cursor: 'pointer',
            fontFamily: 'Inter, sans-serif',
            fontSize: '0.825rem',
            fontWeight: 600,
            transition: 'all 0.2s',
            background: showCavity ? '#15803D' : '#ffffff',
            color: showCavity ? '#ffffff' : '#111827',
            border: showCavity ? 'none' : '1px solid #D1D5DB',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
          }}
        >
          <ArrowUp size={14} /> Cavity
        </button>
      </div>

      {/* View Presets Panel */}
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
      
      {/* Legend overlay */}
      <div className="legend-overlay">
        <div className="legend-item">
          <span className="legend-color" style={{background: '#EF4444', boxShadow: '0 0 8px rgba(239, 68, 68, 0.8)'}}></span>
          Undercuts
        </div>
        <div className="legend-item">
          <span className="legend-line" style={{background: '#3B82F6', boxShadow: '0 0 8px rgba(59, 130, 246, 0.8)'}}></span>
          Parting Line
        </div>
      </div>
    </div>
  );
}
