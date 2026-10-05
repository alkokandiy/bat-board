import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

// A procedural, Tumbler-style armoured Batmobile in WebGL.
//
// Original model built from primitives (no external asset): angular matte-black
// armour, huge exposed rear wheels, small front wheels, a canopy slit, and a
// rear jet turbine. The car faces +X. Units are roughly metres.
//
// Loaded lazily (it pulls in three.js); the timer falls back to its 2D car if
// WebGL is unavailable (`onUnsupported`).

const CANVAS_HEIGHT = 330;

// --- model helpers -----------------------------------------------------------

function extrudeProfile(points, depth, bevel = 0.04) {
  const shape = new THREE.Shape(points.map(([x, y]) => new THREE.Vector2(x, y)));
  const geo = new THREE.ExtrudeGeometry(shape, {
    depth,
    bevelEnabled: bevel > 0,
    bevelSize: bevel,
    bevelThickness: bevel,
    bevelSegments: 2,
    steps: 1,
  });
  geo.translate(0, 0, -depth / 2);
  return geo;
}

function addEdges(mesh, color = 0x5a6e9a, opacity = 0.7) {
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(mesh.geometry, 28),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity }),
  );
  mesh.add(edges);
}

function makeWheel(radius, width, mats, treadCount) {
  const wheel = new THREE.Group();
  const spin = new THREE.Group(); // rotates; the tire's axis is Z
  wheel.add(spin);

  const tire = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, width, 40), mats.rubber);
  tire.rotation.x = Math.PI / 2;
  spin.add(tire);

  // Tread blocks, so the spin is visible.
  const treadGeo = new THREE.BoxGeometry(radius * 0.2, width * 0.94, radius * 0.16);
  const tread = new THREE.InstancedMesh(treadGeo, mats.rubberDark, treadCount);
  const m = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  for (let i = 0; i < treadCount; i++) {
    const a = (i / treadCount) * Math.PI * 2;
    q.setFromAxisAngle(new THREE.Vector3(0, 0, 1), a);
    m.compose(new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0), q, new THREE.Vector3(1, 1, 1));
    tread.setMatrixAt(i, m);
  }
  spin.add(tread);

  // Rim: disc, spokes, glowing hub ring on both faces.
  const rim = new THREE.Mesh(new THREE.CylinderGeometry(radius * 0.62, radius * 0.62, width * 1.02, 32), mats.rim);
  rim.rotation.x = Math.PI / 2;
  spin.add(rim);
  for (const side of [-1, 1]) {
    const z = side * (width / 2 + 0.012);
    for (let i = 0; i < 6; i++) {
      const spoke = new THREE.Mesh(new THREE.BoxGeometry(radius * 1.05, radius * 0.1, 0.02), mats.armor);
      spoke.position.z = z;
      spoke.rotation.z = (i / 6) * Math.PI;
      spin.add(spoke);
    }
    const ring = new THREE.Mesh(new THREE.RingGeometry(radius * 0.2, radius * 0.27, 28), mats.glow);
    ring.position.z = z + side * 0.004;
    if (side < 0) ring.rotation.y = Math.PI;
    spin.add(ring);
  }
  return { group: wheel, spin };
}

function buildBatmobile(mats) {
  const car = new THREE.Group();
  const spinners = []; // [{ spin, speed }]

  // Central tub (side profile, extruded across the width).
  const tubGeo = extrudeProfile(
    [
      [-2.5, 0.5], [2.4, 0.32], [3.3, 0.42], [3.38, 0.62], [2.25, 1.0],
      [0.9, 1.2], [-0.4, 1.3], [-2.2, 1.25], [-2.58, 0.95],
    ],
    1.9,
    0.05,
  );
  const tub = new THREE.Mesh(tubGeo, mats.body);
  tub.castShadow = true;
  addEdges(tub);
  car.add(tub);

  // Hood plate with a slight vent step.
  const hood = new THREE.Mesh(
    extrudeProfile([[1.0, 1.15], [2.35, 0.97], [2.55, 1.04], [1.15, 1.3]], 1.3, 0.03),
    mats.armor,
  );
  addEdges(hood);
  car.add(hood);

  // Canopy: low armoured cockpit with a dark glass slit.
  const canopy = new THREE.Mesh(
    extrudeProfile([[-0.35, 1.28], [0.3, 1.72], [1.55, 1.74], [2.05, 1.12]], 0.95, 0.05),
    mats.glass,
  );
  addEdges(canopy, 0x5b7bb0, 0.5);
  car.add(canopy);
  const visor = new THREE.Mesh(new THREE.BoxGeometry(0.9, 0.05, 0.7), mats.glow);
  visor.position.set(0.95, 1.745, 0);
  car.add(visor);

  // Rear deck spanning between the big fenders.
  const deck = new THREE.Mesh(new THREE.BoxGeometry(2.7, 0.16, 3.5), mats.armor);
  deck.position.set(-1.35, 1.38, 0);
  addEdges(deck);
  car.add(deck);

  // Angular fenders over the rear wheels + side skirts.
  for (const side of [-1, 1]) {
    const fender = new THREE.Mesh(
      extrudeProfile([[-2.55, 1.46], [-2.5, 1.74], [-0.55, 1.8], [0.25, 1.3], [0.12, 1.1], [-0.5, 1.46]], 0.85, 0.04),
      mats.armor,
    );
    fender.position.z = side * 1.55;
    fender.castShadow = true;
    addEdges(fender);
    car.add(fender);

    const skirt = new THREE.Mesh(
      extrudeProfile([[-2.2, 0.55], [1.9, 0.4], [2.5, 0.52], [-2.2, 1.2]], 0.1, 0.02),
      mats.body,
    );
    skirt.position.z = side * 0.99;
    addEdges(skirt, 0x2c3856, 0.5);
    car.add(skirt);
  }

  // Rear wheels: big, wide. Front wheels: small, exposed on struts.
  for (const side of [-1, 1]) {
    const w = makeWheel(0.78, 0.82, mats, 24);
    w.group.position.set(-1.55, 0.78, side * 1.55);
    car.add(w.group);
    spinners.push({ spin: w.spin, r: 0.78 });

    const f = makeWheel(0.46, 0.4, mats, 16);
    f.group.position.set(2.15, 0.46, side * 1.18);
    car.add(f.group);
    spinners.push({ spin: f.spin, r: 0.46 });

    // Front strut + wing plate
    const strut = new THREE.Mesh(new THREE.BoxGeometry(0.2, 0.14, 0.5), mats.armor);
    strut.position.set(2.15, 0.66, side * 0.88);
    car.add(strut);
    const wing = new THREE.Mesh(
      extrudeProfile([[1.5, 0.5], [3.0, 0.38], [3.3, 0.5], [1.7, 0.72]], 0.5, 0.02),
      mats.body,
    );
    wing.position.z = side * 0.78;
    addEdges(wing, 0x2c3856, 0.5);
    car.add(wing);

    // Headlight
    const lamp = new THREE.Mesh(new THREE.BoxGeometry(0.09, 0.1, 0.34), mats.lamp);
    lamp.position.set(3.4, 0.56, side * 0.5);
    car.add(lamp);
  }

  // Rear jet turbine with an animated flame.
  const turbine = new THREE.Group();
  turbine.position.set(-2.95, 0.88, 0);
  const shell = new THREE.Mesh(new THREE.CylinderGeometry(0.44, 0.52, 1.0, 32, 1, true), mats.rim);
  shell.rotation.z = Math.PI / 2;
  turbine.add(shell);
  const core = new THREE.Mesh(new THREE.CircleGeometry(0.42, 32), mats.flameCore);
  core.rotation.y = -Math.PI / 2;
  core.position.x = -0.46;
  turbine.add(core);
  // Teardrop flames (lathe profiles), tip pointing backwards (-X).
  const teardrop = (r, len) => {
    const prof = [[0, 0], [0.9, 0.08], [1, 0.3], [0.78, 0.55], [0.45, 0.78], [0.18, 0.93], [0, 1]]
      .map(([k, t]) => new THREE.Vector2(r * k, len * t));
    return new THREE.LatheGeometry(prof, 24);
  };
  const flame = new THREE.Mesh(teardrop(0.42, 3.4), mats.flame);
  flame.rotation.z = Math.PI / 2; // lathe axis (+Y) → -X
  flame.position.x = -0.5;
  turbine.add(flame);
  const flameInner = new THREE.Mesh(teardrop(0.24, 2.0), mats.flameInner);
  flameInner.rotation.z = Math.PI / 2;
  flameInner.position.x = -0.5;
  turbine.add(flameInner);
  car.add(turbine);

  const flameLight = new THREE.PointLight(0xff7a1a, 0, 9, 2);
  flameLight.position.set(-3.8, 0.9, 0);
  car.add(flameLight);

  const headLight = new THREE.PointLight(0xffe6a0, 1.4, 12, 2);
  headLight.position.set(4.0, 0.7, 0);
  car.add(headLight);

  return { car, spinners, flame, flameInner, core, flameLight };
}

// --- component ---------------------------------------------------------------

export default function Batmobile3D({ progress = 0, running = false, onUnsupported, initialAzimuth = 0.62 }) {
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
    renderer.toneMappingExposure = 1.05;
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;';
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();

    const pmrem = new THREE.PMREMGenerator(renderer);
    const envTex = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environment = envTex;
    scene.environmentIntensity = 0.85;

    const key = new THREE.DirectionalLight(0xfff0d0, 2.6);
    key.position.set(-4, 8, 6);
    scene.add(key);
    const rimBack = new THREE.DirectionalLight(0xffd24a, 2.4);
    rimBack.position.set(6, 3, -7);
    scene.add(rimBack);
    const fillBlue = new THREE.DirectionalLight(0x6f94ff, 0.8);
    fillBlue.position.set(7, 2, 6);
    scene.add(fillBlue);

    const disposables = [envTex, pmrem];
    const mat = (m) => { disposables.push(m); return m; };
    const mats = {
      body: mat(new THREE.MeshStandardMaterial({ color: 0x0b0f18, metalness: 0.65, roughness: 0.42 })),
      armor: mat(new THREE.MeshStandardMaterial({ color: 0x151c2c, metalness: 0.72, roughness: 0.36 })),
      glass: mat(new THREE.MeshStandardMaterial({ color: 0x05080f, metalness: 1, roughness: 0.06, emissive: 0x16263f, emissiveIntensity: 0.5 })),
      rubber: mat(new THREE.MeshStandardMaterial({ color: 0x090a0e, roughness: 0.95, metalness: 0 })),
      rubberDark: mat(new THREE.MeshStandardMaterial({ color: 0x030304, roughness: 1, metalness: 0 })),
      rim: mat(new THREE.MeshStandardMaterial({ color: 0x737c91, metalness: 1, roughness: 0.28 })),
      glow: mat(new THREE.MeshBasicMaterial({ color: 0xffd23a, side: THREE.DoubleSide })),
      lamp: mat(new THREE.MeshBasicMaterial({ color: 0xfff1b8 })),
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
      new THREE.CircleGeometry(6.6, 64),
      // Lambert: no specular, so the low camera angle can't make it glare.
      mat(new THREE.MeshLambertMaterial({ color: 0x0b111f, transparent: true, opacity: 0.8, alphaMap: fadeTex })),
    );
    stage.rotation.x = -Math.PI / 2;
    scene.add(stage);

    const ring = new THREE.Mesh(
      new THREE.RingGeometry(4.9, 4.95, 96),
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
      d.position.set((i - DASH_COUNT / 2) * DASH_GAP, 0.012, -2.9);
      scene.add(d);
      dashes.push(d);
    }

    const { car, spinners, flame, flameInner, core, flameLight } = buildBatmobile(mats);
    scene.add(car);

    // Orbit camera (auto-orbit, drag to look around).
    const camera = new THREE.PerspectiveCamera(32, 2, 0.1, 120);
    const cam = { az: initialAzimuth, el: 0.3, radius: 11.2, drag: false, lastX: 0, lastY: 0, idleUntil: 0 };
    const target = new THREE.Vector3(0.1, 0.45, 0);
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

      // Flame: flicker with throttle.
      const f = speedNow / SPEED;
      const flick = reduceMotion ? 1 : 0.82 + 0.18 * Math.sin(t * 45) + 0.08 * Math.sin(t * 71);
      flame.visible = flameInner.visible = f > 0.03;
      flame.scale.set(Math.max(0.05, f * flick), 0.4 + f * 0.7 * flick, Math.max(0.05, f * flick));
      flameInner.scale.copy(flame.scale);
      mats.flameCore.color.setHex(f > 0.05 ? 0xffd27a : 0x3a2a1a);
      core.scale.setScalar(0.9 + 0.1 * flick * f);
      flameLight.intensity = f * 6 * flick;

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
