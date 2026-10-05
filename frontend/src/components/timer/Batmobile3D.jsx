import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

// A procedural Tumbler-style Batmobile in WebGL (no external asset).
//
// Original model built from primitives (no external asset): angular matte-black
// armour, huge exposed rear wheels, small front wheels, a canopy slit, and a
// rear jet turbine. The car faces +X. Units are roughly metres.
//
// Loaded lazily (it pulls in three.js); the timer falls back to its 2D car if
// WebGL is unavailable (`onUnsupported`).

const CANVAS_HEIGHT = 380;

// --- model helpers -----------------------------------------------------------

function extrudeProfile(points, depth, bevel = 0.03) {
  const shape = new THREE.Shape(points.map(([x, y]) => new THREE.Vector2(x, y)));
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth,
    bevelEnabled: bevel > 0,
    bevelSize: bevel,
    bevelThickness: bevel,
    bevelSegments: 1,
    steps: 1,
  });
  geo.translate(0, 0, -depth / 2);
  return geo;
}

function addEdges(mesh, color = 0x5a6376, opacity = 0.42) {
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry, 25),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity }),
  );
  mesh.add(edges);
}

// A fat, soft off-road tyre: rounded shoulders, a grid of tread blocks, and a
// dished black rim with lug nuts. The wheel's axle is the Z axis.
function makeWheel(R, W, mats) {
  const group = new THREE.Group();
  const spin = new THREE.Group();
  group.add(spin);

  const Ri = R * 0.56; // rim radius
  const h = R - Ri;
  const profile = [
    [Ri, -0.44 * W], [Ri + 0.12 * h, -0.5 * W], [Ri + 0.6 * h, -0.52 * W],
    [R - 0.14 * h, -0.47 * W], [R, -0.36 * W], [R, 0.36 * W], [R - 0.14 * h, 0.47 * W],
    [Ri + 0.6 * h, 0.52 * W], [Ri + 0.12 * h, 0.5 * W], [Ri, 0.44 * W],
  ].map(([x, y]) => new THREE.Vector2(x, y));
  const tire = new THREE.Mesh(new THREE.LatheGeometry(profile, 48), mats.rubber);
  tire.rotation.x = Math.PI / 2;
  spin.add(tire);

  // Tread: three rows of blocks around the crown.
  const COLS = [-0.24, 0, 0.24];
  const PER_ROW = 40;
  const block = new THREE.BoxGeometry(R * 0.05, R * 0.13, W * 0.2);
  const tread = new THREE.InstancedMesh(block, mats.rubberDark, PER_ROW * COLS.length);
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const axis = new THREE.Vector3(0, 0, 1);
  let n = 0;
  COLS.forEach((c, ci) => {
    for (let i = 0; i < PER_ROW; i++) {
      const a = ((i + (ci % 2) * 0.5) / PER_ROW) * Math.PI * 2;
      q.setFromAxisAngle(axis, a);
      m.compose(new THREE.Vector3(Math.cos(a) * (R + R * 0.012), Math.sin(a) * (R + R * 0.012), c * W), q, new THREE.Vector3(1, 1, 1));
      tread.setMatrixAt(n++, m);
    }
  });
  spin.add(tread);

  // Rim: recessed dish, outer lip, lug nuts, centre cap — on both faces.
  for (const side of [-1, 1]) {
    const z = side * W * 0.42;
    const dish = new THREE.Mesh(new THREE.CylinderGeometry(Ri * 0.94, Ri * 0.94, 0.04, 36), mats.rim);
    dish.rotation.x = Math.PI / 2;
    dish.position.z = z;
    spin.add(dish);
    const lip = new THREE.Mesh(new THREE.TorusGeometry(Ri * 0.95, R * 0.035, 8, 36), mats.rim);
    lip.position.z = z + side * 0.015;
    spin.add(lip);
    const cap = new THREE.Mesh(new THREE.CylinderGeometry(Ri * 0.28, Ri * 0.28, 0.07, 20), mats.armor);
    cap.rotation.x = Math.PI / 2;
    cap.position.z = z + side * 0.04;
    spin.add(cap);
    for (let i = 0; i < 6; i++) {
      const a = (i / 6) * Math.PI * 2;
      const nut = new THREE.Mesh(new THREE.CylinderGeometry(R * 0.04, R * 0.04, 0.06, 6), mats.steel);
      nut.rotation.x = Math.PI / 2;
      nut.position.set(Math.cos(a) * Ri * 0.55, Math.sin(a) * Ri * 0.55, z + side * 0.035);
      spin.add(nut);
    }
  }
  return { group, spin };
}

const box = (w, h, d, mat, x, y, z) => {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat);
  mesh.position.set(x, y, z);
  return mesh;
};

// Loft a faceted hull from cross-section rings. Each ring is { x, pts:[[z,y]...] }
// with the same number of points, ordered as a closed loop; this builds the
// side quads and triangle-fan end caps. Lets the body taper to a pointed prow.
function buildLoft(rings, mat) {
  const n = rings[0].pts.length;
  const verts = [];
  const idx = [];
  const start = [];
  for (const r of rings) {
    start.push(verts.length / 3);
    for (const [z, y] of r.pts) verts.push(r.x, y, z);
  }
  for (let s = 0; s < rings.length - 1; s++) {
    const a = start[s];
    const b = start[s + 1];
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      idx.push(a + i, b + j, a + j, a + i, b + i, b + j);
    }
  }
  // Nose cap (fan), then tail cap (reverse winding).
  const caps = [[rings[rings.length - 1], start[rings.length - 1], false], [rings[0], start[0], true]];
  for (const [ring, st, flip] of caps) {
    const c = verts.length / 3;
    let cy = 0, cz = 0;
    for (const [z, y] of ring.pts) { cy += y; cz += z; }
    verts.push(ring.x, cy / n, cz / n);
    for (let i = 0; i < n; i++) {
      const j = (i + 1) % n;
      if (flip) idx.push(c, st + i, st + j);
      else idx.push(c, st + j, st + i);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  const mesh = new THREE.Mesh(g, mat);
  return mesh;
}

// A 10-point faceted cross-section (half-width zw; floor yb, lower yl, upper yu,
// roof yt), ordered clockwise as a closed loop.
function ring(x, zw, yb, yl, yu, yt) {
  return {
    x,
    pts: [
      [0, yt], [zw * 0.55, yt - 0.03], [zw, yu], [zw, yl], [zw * 0.6, yb],
      [0, yb - 0.02], [-zw * 0.6, yb], [-zw, yl], [-zw, yu], [-zw * 0.55, yt - 0.03],
    ],
  };
}

// Tumbler (from a 9-view reference): arrow body — widest at the rear, tapering
// to a low pointed nose — with a narrow small front track, a wide huge rear
// track, a faceted centre-rear greenhouse, a rear roll-cage, and a jet exhaust.
// Car faces +X; units are rough metres.
function buildBatmobile(mats) {
  const car = new THREE.Group();
  const spinners = [];

  // Arrow hull: wide flat rear tapering to a pointed low nose at +X.
  const hull = buildLoft([
    ring(-2.25, 1.36, 0.42, 0.72, 1.02, 1.14),
    ring(-1.45, 1.34, 0.40, 0.70, 1.06, 1.22),
    ring(-0.60, 1.16, 0.40, 0.66, 0.98, 1.10),
    ring(0.30, 0.94, 0.42, 0.62, 0.84, 0.94),
    ring(1.15, 0.68, 0.44, 0.56, 0.70, 0.78),
    ring(1.95, 0.42, 0.46, 0.52, 0.60, 0.66),
    ring(2.60, 0.12, 0.48, 0.50, 0.54, 0.56),
  ], mats.body);
  addEdges(hull, 0x5a6376, 0.28);
  car.add(hull);

  // Splitter / keel under the nose.
  const keel = new THREE.Mesh(
    extrudeProfile([[0.2, 0.34], [2.3, 0.36], [2.68, 0.44], [2.3, 0.52], [0.4, 0.5]], 0.5, 0.03),
    mats.armor,
  );
  addEdges(keel);
  car.add(keel);

  // Faceted greenhouse canopy (centre-rear). The cockpit's dark glass reads as
  // the windscreen on the raked front face — no separate floating pane.
  const canopy = new THREE.Mesh(
    extrudeProfile([[-1.35, 1.02], [-0.25, 1.02], [-0.5, 1.5], [-1.12, 1.5]], 1.26, 0.04),
    mats.canopy,
  );
  addEdges(canopy, 0x47516b, 0.4);
  car.add(canopy);
  for (const side of [-1, 1]) {
    const win = new THREE.Mesh(new THREE.PlaneGeometry(0.82, 0.32), mats.glass);
    win.position.set(-0.82, 1.25, side * 0.64);
    win.rotation.y = side * Math.PI / 2;
    car.add(win);
  }

  // Faceted flank armour, angular rear shrouds, small front covers.
  for (const side of [-1, 1]) {
    const flank = new THREE.Mesh(
      extrudeProfile([[-2.1, 0.44], [1.6, 0.44], [0.9, 0.78], [-0.3, 1.0], [-1.5, 1.02], [-2.15, 0.82]], 0.09, 0.02),
      mats.armor,
    );
    flank.position.z = side * 1.2;
    flank.rotation.x = side * -0.1;
    addEdges(flank);
    car.add(flank);

    const shroud = new THREE.Mesh(
      extrudeProfile([[-2.28, 0.46], [-2.32, 1.16], [-1.72, 1.4], [-0.98, 1.2], [-0.88, 0.85], [-1.5, 0.46]], 0.16, 0.03),
      mats.armor,
    );
    shroud.position.z = side * 1.5;
    addEdges(shroud);
    car.add(shroud);

    const frontCover = new THREE.Mesh(
      extrudeProfile([[0.95, 0.98], [1.05, 1.16], [2.0, 1.0], [2.08, 0.84]], 0.46, 0.02),
      mats.armor,
    );
    frontCover.position.z = side * 0.84;
    addEdges(frontCover);
    car.add(frontCover);
  }

  // Rear deck (engine cover) + a race-style rear wing on two uprights.
  car.add(box(1.6, 0.1, 2.3, mats.armor, -1.6, 1.22, 0));
  const spoiler = new THREE.Group();
  const wing = new THREE.Mesh(
    // thin airfoil (chord along X, slight angle of attack), extruded across the span (Z)
    extrudeProfile([[-0.28, 0.0], [0.28, 0.06], [0.28, 0.15], [-0.28, 0.09]], 2.1, 0.015),
    mats.armor,
  );
  wing.position.set(-2.15, 1.55, 0);
  addEdges(wing);
  spoiler.add(wing);
  for (const z of [-0.82, 0.82]) {
    spoiler.add(box(0.1, 0.5, 0.1, mats.steel, -2.05, 1.3, z)); // upright
  }
  for (const z of [-1.03, 1.03]) {
    spoiler.add(box(0.46, 0.26, 0.03, mats.armor, -2.15, 1.56, z)); // end plate
  }
  car.add(spoiler);

  // Head / tail lamps.
  for (const z of [-0.35, 0.35]) car.add(box(0.06, 0.08, 0.24, mats.lamp, 2.55, 0.6, z));
  for (const z of [-1.15, 1.15]) car.add(box(0.05, 0.12, 0.3, mats.tail, -2.3, 0.78, z));

  // Wheels: small narrow front, huge wide rear.
  for (const side of [-1, 1]) {
    const rear = makeWheel(0.7, 0.8, mats);
    rear.group.position.set(-1.7, 0.7, side * 1.5);
    car.add(rear.group);
    spinners.push({ spin: rear.spin, r: 0.7 });

    const front = makeWheel(0.58, 0.54, mats);
    front.group.position.set(1.62, 0.58, side * 0.84);
    front.group.rotation.x = side * 0.12; // camber: tops lean inward
    car.add(front.group);
    spinners.push({ spin: front.spin, r: 0.58 });
  }

  // --- rear exhaust nozzle with an animated flame (centre) ---
  const turbine = new THREE.Group();
  turbine.position.set(-2.45, 0.74, 0);
  const shell = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.38, 0.5, 28, 1, true), mats.steel);
  shell.rotation.z = Math.PI / 2;
  turbine.add(shell);
  const core = new THREE.Mesh(new THREE.CircleGeometry(0.29, 28), mats.flameCore);
  core.rotation.y = -Math.PI / 2;
  core.position.x = -0.26;
  turbine.add(core);
  const teardrop = (r, len) => {
    const prof = [[0, 0], [0.9, 0.08], [1, 0.3], [0.78, 0.55], [0.45, 0.78], [0.18, 0.93], [0, 1]].map(
      ([k, t]) => new THREE.Vector2(r * k, len * t),
    );
    return new THREE.LatheGeometry(prof, 24);
  };
  const flame = new THREE.Mesh(teardrop(0.3, 3.0), mats.flame);
  flame.rotation.z = Math.PI / 2;
  flame.position.x = -0.26;
  turbine.add(flame);
  const flameInner = new THREE.Mesh(teardrop(0.17, 1.8), mats.flameInner);
  flameInner.rotation.z = Math.PI / 2;
  flameInner.position.x = -0.26;
  turbine.add(flameInner);
  car.add(turbine);

  const flameLight = new THREE.PointLight(0xff7a1a, 0, 9, 2);
  flameLight.position.set(-3.4, 0.8, 0);
  car.add(flameLight);

  const headLight = new THREE.PointLight(0xffe6a0, 1.0, 10, 2);
  headLight.position.set(3.4, 0.7, 0);
  car.add(headLight);

  return { car, spinners, flame, flameInner, core, flameLight };
}

// --- component ---------------------------------------------------------------

export default function Batmobile3D({ progress = 0, running = false, onUnsupported, initialAzimuth = 0.75 }) {
  const mountRef = useRef(null);
  const live = useRef({ running, progress });
  live.current = { running, progress };

  useEffect(() => {
    const mount = mountRef.current;
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    } catch {
      onUnsupported?.();
      return undefined;
    }
    if (!renderer.getContext()) {
      onUnsupported?.();
      return undefined;
    }

    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.9;
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;';
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();

    const pmrem = new THREE.PMREMGenerator(renderer);
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTex;
    scene.environmentIntensity = 0.6;

    const key = new THREE.DirectionalLight(0xe8ecff, 1.25);
    key.position.set(-4, 8, 6);
    scene.add(key);
    const rimBack = new THREE.DirectionalLight(0xffd24a, 0.8);
    rimBack.position.set(6, 3, -7);
    scene.add(rimBack);
    const fillBlue = new THREE.DirectionalLight(0x6f94ff, 0.45);
    fillBlue.position.set(7, 2, 6);
    scene.add(fillBlue);

    const disposables = [envTex, pmrem];
    const mat = (m) => { disposables.push(m); return m; };
    const mats = {
      body: mat(new THREE.MeshStandardMaterial({ color: 0x101319, metalness: 0.25, roughness: 0.66, side: THREE.DoubleSide, flatShading: true })),
      armor: mat(new THREE.MeshStandardMaterial({ color: 0x161a23, metalness: 0.32, roughness: 0.58, flatShading: true })),
      steel: mat(new THREE.MeshStandardMaterial({ color: 0x22262e, metalness: 0.7, roughness: 0.5 })),
      glass: mat(new THREE.MeshStandardMaterial({
        color: 0x7d879a, metalness: 0.2, roughness: 0.12, transparent: true, opacity: 0.62, emissive: 0x1e2533, emissiveIntensity: 0.5,
      })),
      rubber: mat(new THREE.MeshStandardMaterial({ color: 0x0b0b0d, roughness: 0.92, metalness: 0, side: THREE.DoubleSide })),
      rubberDark: mat(new THREE.MeshStandardMaterial({ color: 0x050506, roughness: 1, metalness: 0 })),
      rim: mat(new THREE.MeshStandardMaterial({ color: 0x1c1f26, metalness: 0.9, roughness: 0.4 })),
      canopy: mat(new THREE.MeshStandardMaterial({ color: 0x0b0e15, metalness: 0.15, roughness: 0.72, flatShading: true })),
      lamp: mat(new THREE.MeshBasicMaterial({ color: 0xfff1b8 })),
      tail: mat(new THREE.MeshBasicMaterial({ color: 0xcc1a1a })),
      flameCore: mat(new THREE.MeshBasicMaterial({ color: 0xffb54a, side: THREE.DoubleSide })),
      flame: mat(new THREE.MeshBasicMaterial({
        color: 0xff6a12, transparent: true, opacity: 0.8, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
      })),
      flameInner: mat(new THREE.MeshBasicMaterial({
        color: 0xffe08a, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide,
      })),
    };

    // Stage: a dark platform that fades to transparent at its edge (so it sits
    // on any background), a glowing ring, and lane dashes that scroll while
    // "driving" and fade out with distance.
    const fade = document.createElement('canvas');
    fade.width = fade.height = 256;
    const fctx = fade.getContext('2d');
    const grad = fctx.createRadialGradient(128, 128, 20, 128, 128, 128);
    grad.addColorStop(0, '#fff');
    grad.addColorStop(0.55, '#fff');
    grad.addColorStop(1, '#000');
    fctx.fillStyle = grad;
    fctx.fillRect(0, 0, 256, 256);
    const fadeTex = new THREE.CanvasTexture(fade);
    disposables.push(fadeTex);

    const stage = new THREE.Mesh(
      new THREE.CircleGeometry(4.8, 64),
      // Lambert: no specular, so the low camera angle can't make it glare.
      mat(new THREE.MeshLambertMaterial({ color: 0x0b111f, transparent: true, opacity: 0.8, alphaMap: fadeTex })),
    );
    stage.rotation.x = -Math.PI / 2;
    scene.add(stage);

    const ring = new THREE.Mesh(
      new THREE.RingGeometry(3.85, 3.9, 96),
      mat(new THREE.MeshBasicMaterial({ color: 0xffd23a, transparent: true, opacity: 0.4, side: THREE.DoubleSide })),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.01;
    scene.add(ring);

    const DASH_GAP = 3.2;
    const DASH_COUNT = 7;
    const SPAN = DASH_GAP * DASH_COUNT;
    const dashes = [];
    for (let i = 0; i < DASH_COUNT; i++) {
      const dm = mat(new THREE.MeshBasicMaterial({ color: 0xffd23a, transparent: true, opacity: 0 }));
      const d = new THREE.Mesh(new THREE.BoxGeometry(1.3, 0.012, 0.1), dm);
      d.position.set((i - DASH_COUNT / 2) * DASH_GAP, 0.012, -3.5);
      scene.add(d);
      dashes.push(d);
    }

    // Build the procedural Batmobile.
    const { car, spinners, flame, flameInner, core, flameLight } = buildBatmobile(mats);
    scene.add(car);

    // Orbit camera (auto-orbit, drag to look around).
    const camera = new THREE.PerspectiveCamera(32, 2, 0.1, 120);
    const cam = { az: initialAzimuth, el: 0.22, radius: 8.8, drag: false, lastX: 0, lastY: 0, idleUntil: 0 };
    const target = new THREE.Vector3(0.0, 0.8, 0);
    const placeCamera = () => {
      camera.position.set(
        target.x + cam.radius * Math.cos(cam.el) * Math.cos(cam.az),
        target.y + cam.radius * Math.sin(cam.el),
        target.z + cam.radius * Math.cos(cam.el) * Math.sin(cam.az),
      );
      camera.lookAt(target);
    };

    const resize = () => {
      const w = Math.max(1, mount.clientWidth);
      const h = Math.max(1, mount.clientHeight);
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(mount);

    const el = renderer.domElement;
    const onDown = (e) => { cam.drag = true; cam.lastX = e.clientX; cam.lastY = e.clientY; el.setPointerCapture?.(e.pointerId); el.style.cursor = 'grabbing'; };
    const onMove = (e) => {
      if (!cam.drag) return;
      cam.az -= (e.clientX - cam.lastX) * 0.008;
      cam.el = Math.max(0.05, Math.min(1.1, cam.el + (e.clientY - cam.lastY) * 0.006));
      cam.lastX = e.clientX;
      cam.lastY = e.clientY;
    };
    const onUp = (e) => { cam.drag = false; cam.idleUntil = performance.now() + 3500; el.releasePointerCapture?.(e.pointerId); el.style.cursor = 'grab'; };
    el.style.cursor = 'grab';
    el.style.touchAction = 'pan-y';
    el.addEventListener('pointerdown', onDown);
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('pointercancel', onUp);

    // Animation loop
    let raf = 0;
    let last = performance.now();
    let t = 0;
    const SPEED = 9; // m/s while "driving"
    let speedNow = 0;
    const loop = (now) => {
      raf = requestAnimationFrame(loop);
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      t += dt;
      const { running: isRunning } = live.current;

      // Ease toward the target speed so start/stop feels physical.
      const targetSpeed = isRunning ? SPEED : 0;
      speedNow += (targetSpeed - speedNow) * Math.min(1, dt * 2.5);
      for (const { spin, r } of spinners) spin.rotation.z -= (speedNow / r) * dt;
      for (const d of dashes) {
        d.position.x -= speedNow * dt;
        if (d.position.x < -SPAN / 2) d.position.x += SPAN;
        const edge = 1 - Math.min(1, Math.abs(d.position.x) / (SPAN / 2));
        d.material.opacity = Math.min(0.85, edge * 1.6) * Math.min(1, speedNow / 2);
      }

      // Idle suspension breathing + engine shudder when driving.
      car.position.y = Math.sin(t * 1.4) * 0.008 + (speedNow > 0.5 ? Math.sin(t * 38) * 0.004 : 0);
      car.rotation.z = Math.sin(t * 0.9) * 0.002;

      // Flame: flicker with throttle (procedural model only).
      const f = speedNow / SPEED;
      if (flame) {
        const flick = reduceMotion ? 1 : 0.82 + 0.18 * Math.sin(t * 45) + 0.08 * Math.sin(t * 71);
        flame.visible = flameInner.visible = f > 0.03;
        flame.scale.set(Math.max(0.05, f * flick), 0.4 + f * 0.7 * flick, Math.max(0.05, f * flick));
        flameInner.scale.copy(flame.scale);
        mats.flameCore.color.setHex(f > 0.05 ? 0xffd27a : 0x0d0a07);
        core.scale.setScalar(0.9 + 0.1 * flick * f);
        flameLight.intensity = f * 1.6 * flick;
      }

      // Camera: slow orbit unless the user is dragging.
      if (!cam.drag && !reduceMotion && now > cam.idleUntil) {
        cam.az += dt * (isRunning ? 0.1 : 0.04);
      }
      placeCamera();
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      el.removeEventListener('pointerdown', onDown);
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onUp);
      scene.traverse((o) => {
        if (o.geometry) o.geometry.dispose();
      });
      disposables.forEach((d) => d.dispose?.());
      renderer.dispose();
      renderer.forceContextLoss?.();
      if (el.parentNode === mount) mount.removeChild(el);
    };
  }, [onUnsupported]);

  const p = Math.max(0, Math.min(100, progress));
  return (
    <div className="w-full max-w-[900px] select-none" data-testid="batmobile-3d">
      <div
        ref={mountRef}
        role="img"
        aria-label={`Batmobile, ${Math.round(p)}% of the mission elapsed. Drag to rotate.`}
        style={{ position: 'relative', width: '100%', height: CANVAS_HEIGHT }}
      />
      {/* Mission rail: the bat marker travels with elapsed time */}
      <div style={{ position: 'relative', height: 14, margin: '6px 8px 0' }}>
        <div style={{ position: 'absolute', left: 0, right: 0, top: 6, height: 2, background: 'var(--border-dim)', borderRadius: 1 }} />
        <div
          style={{
            position: 'absolute', left: 0, top: 6, height: 2, width: `${p}%`, borderRadius: 1,
            background: 'linear-gradient(90deg, rgba(255,215,0,0.15), #FFD700)', transition: 'width 0.6s linear',
          }}
        />
        <div
          style={{
            position: 'absolute', top: 1, left: `${p}%`, width: 0, height: 0, transform: 'translateX(-50%)',
            borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderTop: '10px solid #FFD700',
            filter: 'drop-shadow(0 0 6px rgba(255,215,0,0.6))', transition: 'left 0.6s linear',
          }}
        />
      </div>
    </div>
  );
}
