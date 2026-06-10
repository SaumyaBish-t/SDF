/**
 * The hero WebGL scene — a literal visualization of the pipeline.
 *
 * Thousands of particles stream left→right:
 *   · spawn as ember sparks (generator output)
 *   · ~30% flash red and fall at the prefilter ring
 *   · ~25% more die at the scorer ring
 *   · survivors converge, turn green, and are collected into the dataset core
 *
 * All particle motion + fate logic lives in the vertex shader: the CPU does
 * nothing per-frame except advance one uTime uniform, so the main thread
 * stays free for scroll animations.
 */
import { useMemo, useRef } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import * as THREE from "three";
import { heroScroll, pointer, prefersReducedMotion } from "../lib/scrollState";

const VERT = /* glsl */ `
uniform float uTime;
uniform float uPixelRatio;
attribute float aSeed;
attribute float aSpeed;
attribute float aFate;
attribute vec2 aLane;
varying vec3 vColor;
varying float vAlpha;

const float SPAN = 16.0;
const float G1 = -3.0;   // prefilter gate
const float G2 = 1.0;    // scorer gate

void main() {
  float t = fract(aSeed + uTime * aSpeed * 0.05);
  float x = -8.0 + t * SPAN;

  float killX = aFate < 0.30 ? G1 : (aFate < 0.55 ? G2 : 1000.0);

  vec3 pos = vec3(x, aLane.x, aLane.y);

  vec3 ember = vec3(0.984, 0.573, 0.235);
  vec3 hot   = vec3(0.960, 0.620, 0.043);
  vec3 green = vec3(0.133, 0.773, 0.369);
  vec3 red   = vec3(0.937, 0.267, 0.267);

  float alpha = 1.0;
  vec3 col = mix(ember, hot, smoothstep(-8.0, G1, x));

  if (x > killX) {
    // rejected: flash red, fall with gravity, fade out
    float d = x - killX;
    pos.y -= d * d * 0.55;
    col = red;
    alpha = 1.0 - smoothstep(0.0, 2.2, d);
  } else {
    // survivor: converge to the core line after the scorer gate, turn green
    float conv = smoothstep(G2, G2 + 3.0, x);
    pos.y *= 1.0 - conv * 0.85;
    pos.z *= 1.0 - conv * 0.85;
    col = mix(col, green, conv);
    alpha = smoothstep(-8.0, -7.2, x) * (1.0 - smoothstep(6.2, 7.6, x));
  }

  // gentle stream turbulence
  pos.y += sin(x * 0.8 + uTime * 0.6 + aSeed * 6.2831) * 0.12;
  pos.z += cos(x * 0.6 + uTime * 0.5 + aSeed * 6.2831) * 0.12;

  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_Position = projectionMatrix * mv;

  float size = (aFate >= 0.55 && x > G2) ? 2.4 : 1.7;
  float twinkle = 1.0 + 0.35 * sin(uTime * 2.0 + aSeed * 40.0);
  gl_PointSize = size * twinkle * uPixelRatio * (30.0 / -mv.z);

  vColor = col;
  vAlpha = alpha;
}
`;

const FRAG = /* glsl */ `
varying vec3 vColor;
varying float vAlpha;

void main() {
  vec2 uv = gl_PointCoord - 0.5;
  float d = length(uv);
  float a = smoothstep(0.5, 0.05, d) * vAlpha;
  if (a < 0.01) discard;
  gl_FragColor = vec4(vColor, a * 0.85);
}
`;

function ParticleStream({ count }: { count: number }) {
  const matRef = useRef<THREE.ShaderMaterial>(null);

  const { geometry, material } = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const positions = new Float32Array(count * 3); // required attr, unused
    const seeds = new Float32Array(count);
    const speeds = new Float32Array(count);
    const fates = new Float32Array(count);
    const lanes = new Float32Array(count * 2);

    for (let i = 0; i < count; i++) {
      seeds[i] = Math.random();
      speeds[i] = 0.6 + Math.random() * 0.9;
      fates[i] = Math.random();
      // gaussian-ish lane spread around the stream axis
      lanes[i * 2] = (Math.random() + Math.random() + Math.random() - 1.5) * 1.5;
      lanes[i * 2 + 1] = (Math.random() + Math.random() + Math.random() - 1.5) * 1.2;
    }

    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
    geo.setAttribute("aSpeed", new THREE.BufferAttribute(speeds, 1));
    geo.setAttribute("aFate", new THREE.BufferAttribute(fates, 1));
    geo.setAttribute("aLane", new THREE.BufferAttribute(lanes, 2));
    // particles live in shader space — disable culling
    geo.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, 0), 100);

    const mat = new THREE.ShaderMaterial({
      vertexShader: VERT,
      fragmentShader: FRAG,
      uniforms: {
        uTime: { value: prefersReducedMotion ? 25 : 0 },
        uPixelRatio: { value: Math.min(window.devicePixelRatio, 1.75) },
      },
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    return { geometry: geo, material: mat };
  }, [count]);

  useFrame((_, delta) => {
    if (!prefersReducedMotion && matRef.current) {
      matRef.current.uniforms.uTime.value += delta;
    }
  });

  return (
    <points geometry={geometry} frustumCulled={false}>
      <primitive object={material} ref={matRef} attach="material" />
    </points>
  );
}

function Gate({ x, color, label }: { x: number; color: string; label: string }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    if (ref.current && !prefersReducedMotion) {
      ref.current.rotation.x = state.clock.elapsedTime * 0.25;
    }
  });
  return (
    <group position={[x, 0, 0]} name={label}>
      <mesh ref={ref} rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[1.9, 0.025, 12, 72]} />
        <meshBasicMaterial color={color} transparent opacity={0.85} />
      </mesh>
      {/* faint halo ring */}
      <mesh rotation={[0, Math.PI / 2, 0]}>
        <torusGeometry args={[2.05, 0.006, 8, 72]} />
        <meshBasicMaterial color={color} transparent opacity={0.25} />
      </mesh>
    </group>
  );
}

function DatasetCore() {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((state) => {
    if (ref.current && !prefersReducedMotion) {
      const t = state.clock.elapsedTime;
      ref.current.rotation.y = t * 0.4;
      ref.current.rotation.z = t * 0.17;
      const s = 1 + Math.sin(t * 1.6) * 0.06;
      ref.current.scale.setScalar(s);
    }
  });
  return (
    <mesh ref={ref} position={[7, 0, 0]}>
      <icosahedronGeometry args={[0.85, 1]} />
      <meshBasicMaterial color="#22c55e" wireframe transparent opacity={0.7} />
    </mesh>
  );
}

function Rig() {
  const group = useRef<THREE.Group>(null);
  const { camera } = useThree();
  useFrame(() => {
    const p = heroScroll.progress;
    camera.position.z = 11.5 - p * 3.2;
    camera.position.y = 1.0 + p * 1.6;
    camera.lookAt(0, 0, 0);
    if (group.current) {
      // pointer parallax, eased
      group.current.rotation.y += (pointer.x * 0.1 - group.current.rotation.y) * 0.05;
      group.current.rotation.x += (pointer.y * 0.05 - group.current.rotation.x) * 0.05;
    }
  });
  return (
    <group ref={group}>
      <ParticleStream count={window.innerWidth < 768 ? 2200 : 5200} />
      <Gate x={-3} color="#38bdf8" label="prefilter" />
      <Gate x={1} color="#a78bfa" label="scorer" />
      <DatasetCore />
    </group>
  );
}

export default function HeroScene() {
  return (
    <Canvas
      camera={{ position: [0, 1, 11.5], fov: 42 }}
      dpr={[1, 1.75]}
      gl={{ antialias: true, powerPreference: "high-performance", alpha: true }}
      style={{ position: "absolute", inset: 0 }}
      aria-hidden
    >
      <Rig />
    </Canvas>
  );
}
