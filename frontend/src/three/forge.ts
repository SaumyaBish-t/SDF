import * as THREE from "three";

/* ───────────────────────────────────────────────────────────────────────────
   The Forge — a GPU particle knot.

   ~14k points sampled along a (2,3) torus-knot tube. A custom vertex shader
   pushes them through a flowing simplex-noise field; the fragment shader paints
   each point along the triad (generator → prefilter → scorer → gold) and runs a
   bright "refinement" pulse around the knot. Additive blending over obsidian.
   Pointer parallax tilts the whole field. Honors reduced motion.
   ─────────────────────────────────────────────────────────────────────────── */

const snoise = /* glsl */ `
vec3 mod289(vec3 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 mod289(vec4 x){return x-floor(x*(1.0/289.0))*289.0;}
vec4 permute(vec4 x){return mod289(((x*34.0)+1.0)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-0.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1.0/6.0,1.0/3.0); const vec4 D=vec4(0.0,0.5,1.0,2.0);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.0-g; vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289(i);
  vec4 p=permute(permute(permute(i.z+vec4(0.0,i1.z,i2.z,1.0))+i.y+vec4(0.0,i1.y,i2.y,1.0))+i.x+vec4(0.0,i1.x,i2.x,1.0));
  float n_=0.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.0*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.0*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.0-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.0+1.0; vec4 s1=floor(b1)*2.0+1.0; vec4 sh=-step(h,vec4(0.0));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y); vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x; p1*=norm.y; p2*=norm.z; p3*=norm.w;
  vec4 m=max(0.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.0); m=m*m;
  return 42.0*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}
`;

const vertexShader = /* glsl */ `
uniform float uTime;
uniform float uSize;
uniform float uFlow;
attribute float aSeed;
attribute float aLane;
attribute float aScale;
varying float vLane;
varying float vGlow;

${snoise}

void main(){
  vLane = aLane;
  vec3 p = position;

  float t = uTime * 0.16;
  vec3 q = p * 0.5 + vec3(aSeed * 12.0);
  vec3 flow = vec3(
    snoise(q + vec3(0.0, t, 0.0)),
    snoise(q + vec3(t, 0.0, 5.0)),
    snoise(q + vec3(0.0, 5.0, t))
  );
  p += flow * uFlow * (0.5 + aScale);

  // breathing pulse that travels around the knot
  float pulse = sin(aLane * 6.2831 * 3.0 - uTime * 1.4);
  vGlow = smoothstep(0.4, 1.0, pulse);

  vec4 mv = modelViewMatrix * vec4(p, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = uSize * aScale * (1.0 + vGlow * 0.9) * (300.0 / -mv.z);
}
`;

const fragmentShader = /* glsl */ `
precision highp float;
uniform vec3 uGen;
uniform vec3 uPre;
uniform vec3 uSco;
uniform vec3 uGold;
varying float vLane;
varying float vGlow;

void main(){
  vec2 uv = gl_PointCoord - 0.5;
  float d = length(uv);
  if (d > 0.5) discard;
  float alpha = smoothstep(0.5, 0.0, d);

  // triad gradient across the lane, gold accents on the pulse crest
  vec3 col;
  if (vLane < 0.5) col = mix(uGen, uPre, smoothstep(0.0, 0.5, vLane));
  else col = mix(uPre, uSco, smoothstep(0.5, 1.0, vLane));
  col = mix(col, uGold, vGlow * 0.55);
  col += vGlow * 0.25;

  gl_FragColor = vec4(col, alpha * (0.35 + vGlow * 0.65));
}
`;

export class Forge {
  private renderer: THREE.WebGLRenderer;
  private scene = new THREE.Scene();
  private camera: THREE.PerspectiveCamera;
  private points: THREE.Points;
  private material: THREE.ShaderMaterial;
  private group = new THREE.Group();
  private raf = 0;
  private clock = new THREE.Clock();
  private pointer = new THREE.Vector2(0, 0);
  private pointerTarget = new THREE.Vector2(0, 0);
  private reduced: boolean;
  private parent: HTMLElement;

  constructor(canvas: HTMLCanvasElement, reduced = false) {
    this.reduced = reduced;
    this.parent = canvas.parentElement ?? document.body;

    this.renderer = new THREE.WebGLRenderer({
      canvas,
      alpha: true,
      antialias: false,
      powerPreference: "high-performance",
    });
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    this.camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100);
    this.camera.position.set(0, 0, 11);

    const { geometry, material } = this.build();
    this.material = material;
    this.points = new THREE.Points(geometry, material);
    this.group.add(this.points);
    this.scene.add(this.group);

    this.resize();
    window.addEventListener("resize", this.resize);
    window.addEventListener("pointermove", this.onPointer);

    if (this.reduced) this.renderOnce();
    else this.loop();
  }

  private build() {
    const COUNT = window.innerWidth < 640 ? 8000 : 14000;
    const positions = new Float32Array(COUNT * 3);
    const seeds = new Float32Array(COUNT);
    const lanes = new Float32Array(COUNT);
    const scales = new Float32Array(COUNT);

    const p = 2,
      q = 3;
    const R = 3.2,
      tube = 1.0;

    for (let i = 0; i < COUNT; i++) {
      const u = (i / COUNT) * Math.PI * 2 * q;
      // torus-knot centerline
      const cu = Math.cos(u),
        su = Math.sin(u),
        qpu = (q / p) * u;
      const cqp = Math.cos(qpu),
        sqp = Math.sin(qpu);
      const cx = (R + tube * cqp) * cu;
      const cy = (R + tube * cqp) * su;
      const cz = tube * sqp;

      // scatter inside a fuzzy tube around the centerline
      const rr = Math.pow(Math.random(), 0.5) * 0.95;
      const a = Math.random() * Math.PI * 2;
      positions[i * 3] = cx + Math.cos(a) * rr;
      positions[i * 3 + 1] = cy + Math.sin(a) * rr;
      positions[i * 3 + 2] = cz + (Math.random() - 0.5) * 1.6;

      seeds[i] = Math.random();
      lanes[i] = (i / COUNT) % 1; // sweeps the triad around the knot
      scales[i] = 0.4 + Math.random() * 1.4;
    }

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
    geometry.setAttribute("aLane", new THREE.BufferAttribute(lanes, 1));
    geometry.setAttribute("aScale", new THREE.BufferAttribute(scales, 1));

    const material = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uSize: { value: window.innerWidth < 640 ? 2.2 : 2.8 },
        uFlow: { value: this.reduced ? 0.35 : 0.9 },
        uGen: { value: new THREE.Color("#2bf5a0") },
        uPre: { value: new THREE.Color("#3aa0ff") },
        uSco: { value: new THREE.Color("#ff5d73") },
        uGold: { value: new THREE.Color("#ffd27a") },
      },
      vertexShader,
      fragmentShader,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });

    return { geometry, material };
  }

  private onPointer = (e: PointerEvent) => {
    this.pointerTarget.set(
      (e.clientX / window.innerWidth) * 2 - 1,
      (e.clientY / window.innerHeight) * 2 - 1,
    );
  };

  private resize = () => {
    const w = this.parent.clientWidth || window.innerWidth;
    const h = this.parent.clientHeight || window.innerHeight;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (this.reduced) this.renderOnce();
  };

  private renderOnce() {
    this.material.uniforms.uTime.value = 8.0;
    this.group.rotation.set(0.35, 0.6, 0);
    this.renderer.render(this.scene, this.camera);
  }

  private loop = () => {
    this.raf = requestAnimationFrame(this.loop);
    const t = this.clock.getElapsedTime();
    this.material.uniforms.uTime.value = t;

    this.pointer.lerp(this.pointerTarget, 0.04);
    this.group.rotation.y = t * 0.06 + this.pointer.x * 0.5;
    this.group.rotation.x = 0.2 + this.pointer.y * 0.3;

    this.renderer.render(this.scene, this.camera);
  };

  dispose() {
    cancelAnimationFrame(this.raf);
    window.removeEventListener("resize", this.resize);
    window.removeEventListener("pointermove", this.onPointer);
    this.points.geometry.dispose();
    this.material.dispose();
    this.renderer.dispose();
  }
}
