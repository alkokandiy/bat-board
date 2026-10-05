import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js';

// Compressed real model of The Batman (2022) Batmobile, served as a static
// asset. Loaded on demand; the procedural model below is the fallback if the
// file or WebGL can't load. Draco decoder is hosted alongside.
const MODEL_URL = '/models/batmobile.glb';
const DRACO_PATH = '/draco/';

// Real 2022 Batmobile (glTF) with a procedural fallback, in WebGL.
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

// Tumbler: low faceted tub tapering to a pointed prow, a low canopy set back,
// huge rear wheels under angular shrouds, big exposed canted front wheels, and
// a tubular roll-cage on the rear deck. Car faces +X; units are rough metres.
function buildBatmobile(mats) {
  const car = new THREE.Group();
  const spinners = [];

  // --- main hull (lofted, tail at -X to a near-point prow at +X) ---
  const hull = buildLoft([
    ring(-2.35, 0.96, 0.50, 0.80, 1.10, 1.22),
    ring(-1.60, 1.14, 0.40, 0.74, 1.16, 1.34),
    ring(-0.80, 1.20, 0.36, 0.70, 1.16, 1.38),
    ring(0.00, 1.20, 0.36, 0.68, 1.12, 1.34),
    ring(0.80, 1.06, 0.38, 0.64, 1.00, 1.18),
    ring(1.60, 0.88, 0.40, 0.58, 0.84, 0.98),
    ring(2.35, 0.52, 0.42, 0.50, 0.62, 0.70),
    ring(3.05, 0.12, 0.40, 0.42, 0.46, 0.48),
  ], mats.body);
  addEdges(hull, 0x5a6376, 0.3);
  car.add(hull);

  // Angular belly plate under the prow (the Tumbler's keel).
  const keel = new THREE.Mesh(
    extrudeProfile([[0.4, 0.34], [2.7, 0.36], [3.1, 0.44], [2.7, 0.52], [0.6, 0.5]], 0.42, 0.03),
    mats.armor,
  );
  addEdges(keel);
  car.add(keel);

  // --- low faceted canopy, set back, with a gold-tinted windscreen ---
  const canopy = new THREE.Mesh(new THREE.IcosahedronGeometry(0.66, 1), mats.canopy);
  canopy.scale.set(1.5, 0.5, 0.88);
  canopy.position.set(0.0, 1.42, 0);
  addEdges(canopy, 0x47516b, 0.35);
  car.add(canopy);
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(0.62, 0.42), mats.goldGlass);
  screen.position.set(0.74, 1.46, 0);
  screen.rotation.y = -Math.PI / 2;
  screen.rotation.z = -0.7;
  car.add(screen);

  // --- faceted side armour panels + rear shrouds over the big wheels ---
  for (const side of [-1, 1]) {
    const flank = new THREE.Mesh(
      extrudeProfile([[-2.0, 0.46], [1.9, 0.44], [1.5, 0.78], [0.6, 1.08], [-0.4, 1.22], [-1.6, 1.12], [-2.05, 0.82]], 0.09, 0.02),
      mats.armor,
    );
    flank.position.z = side * 1.08;
    flank.rotation.x = side * -0.12;
    addEdges(flank);
    car.add(flank);

    const chine = new THREE.Mesh(
      extrudeProfile([[-1.5, 0.4], [1.8, 0.4], [2.3, 0.56], [1.4, 0.64], [-1.2, 0.6]], 0.1, 0.02),
      mats.steel,
    );
    chine.position.z = side * 1.12;
    car.add(chine);

    // Rear wheel shroud: an angular plate wrapping the top/outside of the tyre.
    const shroud = new THREE.Mesh(
      extrudeProfile([[-2.5, 0.55], [-2.55, 1.5], [-1.95, 1.72], [-1.05, 1.56], [-0.9, 1.05], [-1.6, 0.55]], 0.14, 0.03),
      mats.armor,
    );
    shroud.position.z = side * 1.46;
    addEdges(shroud);
    car.add(shroud);

    // Suspension A-arms out to the exposed front wheels.
    for (const dy of [-0.12, 0.12]) {
      const arm = box(0.5, 0.1, 0.12, mats.steel, 2.05, 0.66 + dy, side * 1.12);
      arm.rotation.y = side * 0.3;
      car.add(arm);
    }
  }

  // --- tubular roll-cage on the rear deck, swept up and back ---
  car.add(box(1.5, 0.12, 2.0, mats.armor, -1.7, 1.42, 0));
  const cage = new THREE.Group();
  const tube = (len, x, y, z, rz = 0, ry = 0) => {
    const t = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, len, 10), mats.steel);
    t.position.set(x, y, z);
    t.rotation.z = rz;
    t.rotation.y = ry;
    return t;
  };
  for (const z of [-0.78, 0.78]) {
    cage.add(tube(1.4, -1.6, 1.74, z, Math.PI / 2 - 0.42)); // swept side rail
    cage.add(tube(0.42, -1.05, 1.58, z, 0.5)); // front leg
    cage.add(tube(0.5, -2.28, 1.6, z, -0.2)); // rear leg
  }
  cage.add(tube(1.58, -1.6, 2.0, 0, 0, Math.PI / 2)); // top cross-tube (front)
  cage.add(tube(1.58, -2.28, 1.78, 0, 0, Math.PI / 2)); // top cross-tube (rear)
  car.add(cage);

  // --- head/tail lamps ---
  for (const z of [-0.42, 0.42]) car.add(box(0.06, 0.08, 0.26, mats.lamp, 2.78, 0.62, z));
  for (const z of [-1.0, 1.0]) car.add(box(0.05, 0.12, 0.3, mats.tail, -2.4, 0.78, z));

  // --- wheels: huge rear, big exposed canted front ---
  for (const side of [-1, 1]) {
    const rear = makeWheel(0.82, 0.82, mats);
    rear.group.position.set(-1.75, 0.82, side * 1.5);
    car.add(rear.group);
    spinners.push({ spin: rear.spin, r: 0.82 });

    const front = makeWheel(0.72, 0.62, mats);
    front.group.position.set(2.2, 0.72, side * 1.44);
    front.group.rotation.x = side * 0.1; // camber: tops lean inward
    car.add(front.group);
    spinners.push({ spin: front.spin, r: 0.72 });
  }

  // --- rear exhaust nozzle with an animated flame ---
  const turbine = new THREE.Group();
  turbine.position.set(-2.5, 0.72, 0);
  const shell = new THREE.Mesh(new THREE.CylinderGeometry(0.28, 0.36, 0.5, 28, 1, true), mats.steel);
  shell.rotation.z = Math.PI / 2;
  turbine.add(shell);
  const core = new THREE.Mesh(new THREE.CircleGeometry(0.27, 28), mats.flameCore);
  core.rotation.y = -Math.PI / 2;
  core.position.x = -0.26;
  turbine.add(core);
  const teardrop = (r, len) => {
    const prof = [[0, 0], [0.9, 0.08], [1, 0.3], [0.78, 0.55], [0.45, 0.78], [0.18, 0.93], [0, 1]].map(
      ([k, t]) => new THREE.Vector2(r * k, len * t),
    );
    return new THREE.LatheGeometry(prof, 24);
  };
  const flame = new THREE.Mesh(teardrop(0.28, 3.0), mats.flame);
  flame.rotation.z = Math.PI / 2;
  flame.position.x = -0.26;
  turbine.add(flame);
  const flameInner = new THREE.Mesh(teardrop(0.16, 1.8), mats.flameInner);
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

export default function Batmobile3D({ progress = 0, running = false, onUnsupported, initialAzimuth = 5.5 }) {
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
    renderer.toneMappingExposure = 1.0;
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;';
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();

    const pmrem = new THREE.PMREMGenerator(renderer);
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTex;
    scene.environmentIntensity = 0.9;

    const key = new THREE.DirectionalLight(0xe8ecff, 1.5);
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
      body: mat(new THREE.MeshStandardMaterial({ color: 0x14171e, metalness: 0.28, roughness: 0.62, side: THREE.DoubleSide, flatShading: true })),
      armor: mat(new THREE.MeshStandardMaterial({ color: 0x1c212b, metalness: 0.35, roughness: 0.55, flatShading: true })),
      steel: mat(new THREE.MeshStandardMaterial({ color: 0x22262e, metalness: 0.7, roughness: 0.5 })),
      glass: mat(new THREE.MeshStandardMaterial({
        color: 0x7d879a, metalness: 0.2, roughness: 0.12, transparent: true, opacity: 0.62, emissive: 0x1e2533, emissiveIntensity: 0.5,
      })),
      rubber: mat(new THREE.MeshStandardMaterial({ color: 0x0b0b0d, roughness: 0.92, metalness: 0, side: THREE.DoubleSide })),
      rubberDark: mat(new THREE.MeshStandardMaterial({ color: 0x050506, roughness: 1, metalness: 0 })),
      rim: mat(new THREE.MeshStandardMaterial({ color: 0x1c1f26, metalness: 0.9, roughness: 0.4 })),
      canopy: mat(new THREE.MeshStandardMaterial({ color: 0x0e1016, metalness: 0.5, roughness: 0.35, emissive: 0x05070b, emissiveIntensity: 0.4, flatShading: true })),
      goldGlass: mat(new THREE.MeshStandardMaterial({ color: 0x8a6a2a, metalness: 0.6, roughness: 0.2, transparent: true, opacity: 0.72, emissive: 0x3a2c10, emissiveIntensity: 0.5, side: THREE.DoubleSide })),
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

    // Car group. Start with the procedural model so something shows instantly,
    // then swap in the real glTF model once it downloads. If the model fails,
    // the procedural one stays.
    const car = new THREE.Group();
    scene.add(car);
    let spinners = [];
    let flame = null, flameInner = null, core = null, flameLight = null;
    let usingModel = false;

    const useProcedural = () => {
      const b = buildBatmobile(mats);
      car.add(b.car);
      ({ spinners, flame, flameInner, core, flameLight } = b);
    };
    useProcedural();

    // Fit the real model: scale to the stage, drop onto the ground, and lay its
    // longest horizontal axis along X (the car's length).
    const fitModel = (obj) => {
      let box = new THREE.Box3().setFromObject(obj);
      const size = box.getSize(new THREE.Vector3());
      if (size.z > size.x) obj.rotation.y = Math.PI / 2;
      box = new THREE.Box3().setFromObject(obj);
      const s2 = box.getSize(new THREE.Vector3());
      const c = box.getCenter(new THREE.Vector3());
      const scale = 5.8 / Math.max(s2.x, s2.z);
      obj.scale.setScalar(scale);
      obj.position.set(-c.x * scale, -box.min.y * scale, -c.z * scale);
    };

    const draco = new DRACOLoader();
    draco.setDecoderPath(DRACO_PATH);
    const gltfLoader = new GLTFLoader();
    gltfLoader.setDRACOLoader(draco);
    gltfLoader.load(
      MODEL_URL,
      (gltf) => {
        // Drop the procedural stand-in and its geometries.
        car.traverse((o) => { if (o.geometry && o !== car) o.geometry.dispose(); });
        car.clear();
        spinners = [];
        flame = flameInner = core = flameLight = null;
        gltf.scene.traverse((o) => { o.castShadow = false; o.receiveShadow = false; });
        fitModel(gltf.scene);
        car.add(gltf.scene);
        usingModel = true;
        draco.dispose();
      },
      undefined,
      () => { draco.dispose(); }, // keep the procedural model on any load error
    );

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
      {/* CC BY attribution for the 3D model (required by its licence). */}
      <div style={{ textAlign: 'center', marginTop: 6, fontSize: 9, lineHeight: 1.4, color: 'var(--text-muted, #64748b)' }}>
        <a href="https://sketchfab.com/3d-models/the-batman-2022-batmobile-53ee4c6aa8df4315993a99f0fddb35c9"
           target="_blank" rel="noopener noreferrer"
           style={{ color: 'inherit', textDecoration: 'underline' }}>
          “The Batman 2022 – Batmobile”
        </a>{' '}by{' '}
        <a href="https://sketchfab.com/ImADefaultCube117"
           target="_blank" rel="noopener noreferrer"
           style={{ color: 'inherit', textDecoration: 'underline' }}>
          ImADefaultCube117
        </a>{' '}·{' '}
        <a href="https://creativecommons.org/licenses/by/4.0/"
           target="_blank" rel="noopener noreferrer"
           style={{ color: 'inherit', textDecoration: 'underline' }}>
          CC BY 4.0
        </a>{' '}· via Sketchfab
      </div>
    </div>
  );
}
