import React, { useState, useEffect, useRef, useCallback } from 'react';
import { trackPresets } from './AudioPlayer';

const PHASES = [
  { id: 0, label: 'PREP', name: 'PREPARATION', dur: 10 * 60, type: 'prep', isBomb: false },
  { id: 1, label: 'WORK', name: 'ENGAGEMENT I', dur: 50 * 60, type: 'work', isBomb: false },
  { id: 2, label: 'BREAK', name: 'REGROUP', dur: 10 * 60, type: 'break', isBomb: false },
  { id: 3, label: 'WORK', name: 'ENGAGEMENT II', dur: 50 * 60, type: 'work', isBomb: false },
  { id: 4, label: 'BREAK', name: 'RELOAD', dur: 10 * 60, type: 'break', isBomb: false },
  { id: 5, label: 'WORK', name: 'ENGAGEMENT III', dur: 50 * 60, type: 'work', isBomb: false },
  { id: 6, label: 'BREAK', name: 'EXFILTRATION', dur: 20 * 60, type: 'exfil', isBomb: true },
];

const QUOTES = [
  { t: '"Whoever comes, whoever it is... I\'ll kill them. I\'ll kill them all."', a: '— John Wick' },
  { t: '"Be focused. Be exceptional."', a: '— John Wick' },
  { t: '"Whatever is in front of you, push through."', a: '— John Wick' },
  { t: '"I need a focus. Give me a focus."', a: '— John Wick' },
  { t: '"You stabbed the devil in the back."', a: '— Winston' },
  { t: '"Consequences. There are always consequences."', a: '— John Wick' },
  { t: '"I\'ll take it from here."', a: '— John Wick' },
];

const TRANS_DATA = [
  { code: 'PHASE 1 COMPLETE', title: 'WEAPONS\nLOADED', sub: 'Preparation done. Time to work.', next: 'NEXT: ENGAGEMENT I — 50 MIN' },
  { code: 'ENGAGEMENT I DONE', title: 'TARGET\nNEUTRALIZED', sub: 'First wave down. Regroup.', next: 'NEXT: REGROUP — 10 MIN' },
  { code: 'REGROUP COMPLETE', title: 'BACK\nIN ACTION', sub: 'Loaded up. Round two.', next: 'NEXT: ENGAGEMENT II — 50 MIN' },
  { code: 'ENGAGEMENT II DONE', title: 'SECOND\nACT CLOSED', sub: 'Hold the line. Almost there.', next: 'NEXT: RELOAD — 10 MIN' },
  { code: 'RELOAD COMPLETE', title: 'FINAL\nSTAND', sub: 'Last engagement. Make it count.', next: 'NEXT: ENGAGEMENT III — 50 MIN' },
  { code: 'ENGAGEMENT III DONE', title: 'LAST\nMAN DOWN', sub: 'The hard work is done.', next: 'NEXT: EXFILTRATION — 20 MIN' },
];

const VIDEOS = [
  { src: '', label: 'PREPARING FOR WAR' },
  { src: '', label: 'ELIMINATING TARGETS' },
  { src: '', label: 'TACTICAL RELOAD' },
  { src: '', label: 'SECOND ASSAULT' },
  { src: '', label: 'CATCHING BREATH' },
  { src: '', label: 'FINAL ENGAGEMENT' },
  { src: '', label: 'EXFILTRATING' },
];

export default function JohnWickPanel({ activeTrack, isPlaying, onTrackChange }) {
  const [page, setPage] = useState('landing');
  const [mission, setMission] = useState('');
  const [missionInput, setMissionInput] = useState('');
  const [phase, setPhase] = useState(0);
  const [timeLeft, setTimeLeft] = useState(0);
  const [running, setRunning] = useState(false);
  const [flashColor, setFlashColor] = useState(null);

  const timerRef = useRef(null);
  const canvasRef = useRef(null);
  const bloodBgRef = useRef(null);
  const cylinderAngleRef = useRef(0);
  const videoRef = useRef(null);

  // BG CANVAS
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let parts = [];
    let animId;

    const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
    resize();
    window.addEventListener('resize', resize);

    for (let i = 0; i < 60; i++) {
      parts.push({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        r: Math.random() * 1.5 + 0.3,
        vx: (Math.random() - 0.5) * 0.2,
        vy: Math.random() * 0.15 + 0.05,
        alpha: Math.random() * 0.4 + 0.1,
        color: Math.random() > 0.6 ? '#c0112b' : '#d4a017',
      });
    }

    const draw = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      parts.forEach(p => {
        ctx.save();
        ctx.globalAlpha = p.alpha;
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = 4;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
        p.x += p.vx;
        p.y += p.vy;
        if (p.y > canvas.height + 10) { p.y = -5; p.x = Math.random() * canvas.width; }
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1;
      });
      animId = requestAnimationFrame(draw);
    };
    draw();

    return () => { cancelAnimationFrame(animId); window.removeEventListener('resize', resize); };
  }, []);

  // BLOOD DRIPS
  useEffect(() => {
    if (!bloodBgRef.current) return;
    const dripContainer = bloodBgRef.current;
    let dripIntervals = [];

    const timeouts = [];

    const spawnDrip = () => {
      const d = document.createElement('div');
      d.className = 'jw-drip';
      d.style.left = Math.random() * 100 + 'vw';
      const h = Math.random() * 30 + 10;
      d.style.height = h + 'vh';
      d.style.width = (Math.random() * 3 + 1) + 'px';
      const dur = Math.random() * 6 + 4;
      d.style.animationDuration = dur + 's';
      d.style.animationDelay = (Math.random() * 8) + 's';
      d.style.opacity = (Math.random() * 0.5 + 0.2) + '';
      dripContainer.appendChild(d);
      timeouts.push(setTimeout(() => d.remove(), (dur + 8) * 1000));
    };

    for (let i = 0; i < 20; i++) spawnDrip();
    const interval = setInterval(spawnDrip, 800);

    return () => {
      clearInterval(interval);
      timeouts.forEach(clearTimeout);
      dripContainer.innerHTML = '';
    };
  }, [page]);

  // TIMER
  useEffect(() => {
    if (!running || timeLeft <= 0) return;
    timerRef.current = setInterval(() => {
      setTimeLeft(prev => prev - 1);
      cylinderAngleRef.current += 0.3;
    }, 1000);
    return () => clearInterval(timerRef.current);
  }, [running]);

  // AUTO-ADVANCE when timer runs out
  useEffect(() => {
    if (timeLeft === 0 && page === 'running') {
      setRunning(false);
      onPhaseEnd();
    }
  }, [timeLeft, page]);

  // FLASH
  const flash = useCallback((color, ms) => {
    setFlashColor(color);
    setTimeout(() => setFlashColor(null), ms);
  }, []);

  // START MISSION
  const startMission = () => {
    const name = missionRef.current.trim() || 'Unnamed Target';
    setMission(name);
    flash('#c0112b', 200);
    setTimeout(() => {
      setPhase(0);
      setTimeLeft(PHASES[0].dur);
      setRunning(false);
      setPage('focus');
    }, 250);
  };

  // TOGGLE TIMER
  const toggleTimer = () => {
    if (!running && timeLeft === 0) {
      const p = PHASES[phase];
      setTimeLeft(p.dur);
    }
    setRunning(prev => !prev);
  };

  // SKIP PHASE
  const skipPhase = () => {
    setRunning(false);
    clearInterval(timerRef.current);
    onPhaseEnd();
  };

  // ABORT
  const abortMission = () => {
    if (!window.confirm('Abort the contract?')) return;
    setRunning(false);
    clearInterval(timerRef.current);
    setPage('landing');
  };

  // PHASE END
  const onPhaseEnd = () => {
    flash(PHASES[phase].type === 'work' ? '#c0112b' : '#d4a017', 300);
    if (phase >= PHASES.length - 1) {
      setTimeout(() => { setPage('complete'); setRunning(false); }, 400);
      return;
    }
    setTimeout(() => { setPage('transition'); setRunning(false); }, 400);
  };

  // CONTINUE TO NEXT PHASE
  const continueToNext = () => {
    const nextPhase = phase + 1;
    if (nextPhase >= PHASES.length) return;
    setPhase(nextPhase);
    setTimeLeft(PHASES[nextPhase].dur);
    setRunning(false);
    setPage('focus');
    flash('#d4a017', 200);
  };

  // NEW MISSION
  const newMission = () => {
    setRunning(false);
    clearInterval(timerRef.current);
    setMissionInput('');
    setPage('landing');
  };

  // VIDEO LOADING
  useEffect(() => {
    if (page !== 'focus' || !videoRef.current) return;
    const vid = videoRef.current;
    const entry = VIDEOS[phase] || {};
    const holder = document.getElementById('jw-video-placeholder');
    const animLabel = document.getElementById('jw-anim-label');

    if (animLabel) animLabel.textContent = entry.label || '';

    if (entry.src && entry.src.trim() !== '') {
      vid.src = entry.src;
      vid.style.display = 'block';
      if (holder) holder.style.display = 'none';
      vid.load();
      vid.play().catch(() => {
        if (holder) {
          holder.style.display = 'flex';
          holder.querySelector('.jw-vp-text').innerHTML = 'TAP TO PLAY<span>' + entry.src + '</span>';
          holder.style.cursor = 'pointer';
          holder.onclick = () => { vid.play(); holder.style.display = 'none'; };
        }
      });
    } else {
      vid.style.display = 'none';
      vid.src = '';
      if (holder) {
        holder.style.display = 'flex';
        holder.querySelector('.jw-vp-text').innerHTML =
          'ADD YOUR VIDEO CLIPS HERE' +
          '<span>Set src in the VIDEOS array.<br>Phase ' + phase + ': edit VIDEOS[' + phase + '].src<br>Format: MP4</span>';
        holder.onclick = null;
        holder.style.cursor = 'default';
      }
    }
  }, [phase, page]);

  const missionRef = useRef(missionInput);
  missionRef.current = missionInput;

  // KEYBOARD
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 'Enter' && page === 'landing') startMission();
      if (e.key === ' ' && page === 'focus') { e.preventDefault(); toggleTimer(); }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [page]);

  const formatTime = (s) => {
    const m = Math.floor(s / 60).toString().padStart(2, '0');
    const sec = (s % 60).toString().padStart(2, '0');
    return m + ':' + sec;
  };

  const p = PHASES[phase];
  const pct = p ? 1 - (timeLeft / p.dur) : 0;

  return (
    <div className="jw-root" style={{ paddingBottom: '60px' }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Playfair+Display:ital,wght@0,900;1,900&family=Share+Tech+Mono&family=Cinzel:wght@900&display=swap');

        .jw-root {
          --blood: #7a0000;
          --blood2: #c0112b;
          --gold: #d4a017;
          --gold2: #f5c842;
          --jw-dark: #060608;
          --darker: #030304;
          --charcoal: #111115;
          --smoke: #1c1c22;
          --jw-text: #c8bfa8;
          --text2: #7a7060;
          --white: #ede8de;
          position: relative;
          width: 100%;
          height: 100%;
          min-height: calc(100vh - 8rem);
          background: var(--darker);
          overflow: hidden;
          font-family: 'Share Tech Mono', monospace;
          cursor: crosshair;
          color: var(--jw-text);
        }
        .jw-root * { margin: 0; padding: 0; box-sizing: border-box; }
        .jw-bg-canvas { position: absolute; inset: 0; z-index: 0; pointer-events: none; }
        .jw-grain { position: absolute; inset: 0; z-index: 200; pointer-events: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='300' height='300'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.75' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='300' height='300' filter='url(%23n)' opacity='0.07'/%3E%3C/svg%3E"); opacity: 0.5; mix-blend-mode: overlay; }
        .jw-vignette { position: absolute; inset: 0; z-index: 199; pointer-events: none; background: radial-gradient(ellipse at 50% 50%, transparent 35%, rgba(0,0,0,0.92) 100%); }
        .jw-scanlines { position: absolute; inset: 0; z-index: 198; pointer-events: none; background: repeating-linear-gradient(0deg, rgba(0,0,0,0.03) 0px, rgba(0,0,0,0.03) 1px, transparent 1px, transparent 4px); }
        .jw-page { position: absolute; inset: 0; z-index: 10; display: flex; align-items: center; justify-content: center; opacity: 0; pointer-events: none; transition: opacity 0.6s ease; }
        .jw-page.active { opacity: 1; pointer-events: all; }
        .jw-blood-bg { position: absolute; inset: 0; z-index: 1; pointer-events: none; overflow: hidden; }
        .jw-drip { position: absolute; top: 0; width: 2px; background: linear-gradient(to bottom, var(--blood2), var(--blood), transparent); border-radius: 0 0 50% 50%; animation: jw-drip-fall linear infinite; opacity: 0; }
        @keyframes jw-drip-fall { 0%{height:0;opacity:0;transform:translateY(-20px)} 5%{opacity:0.8} 85%{opacity:0.6} 100%{height:40vh;opacity:0;transform:translateY(0)} }
        .jw-continental-bg { position: absolute; inset: 0; z-index: 2; pointer-events: none; display: flex; align-items: center; justify-content: center; }
        .jw-seal { width: 500px; height: 500px; opacity: 0.04; animation: jw-seal-rotate 60s linear infinite; }
        @keyframes jw-seal-rotate { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
        .jw-landing { flex-direction: column; }
        .jw-landing-inner { position: relative; z-index: 10; display: flex; flex-direction: column; align-items: center; gap: 0; animation: jw-fadeSlideUp 1s ease both; }
        @keyframes jw-fadeSlideUp { from{opacity:0;transform:translateY(40px)} to{opacity:1;transform:translateY(0)} }
        .jw-badge { font-family: 'Cinzel', serif; font-size: 10px; letter-spacing: 8px; color: var(--gold); margin-bottom: 18px; opacity: 0.7; animation: jw-fadeSlideUp 1s 0.2s ease both; }
        .jw-hero-title { font-family: 'Bebas Neue', sans-serif; font-size: clamp(80px, 12vw, 140px); line-height: 0.85; color: var(--white); text-shadow: 0 0 40px rgba(212,160,23,0.3), 0 0 80px rgba(192,17,43,0.2); letter-spacing: 6px; animation: jw-fadeSlideUp 1s 0.1s ease both; }
        .jw-hero-title span { display: block; font-size: 0.32em; letter-spacing: 18px; color: var(--gold); text-shadow: 0 0 20px rgba(212,160,23,0.6); }
        .jw-rule { width: 100%; height: 1px; margin: 22px 0; background: linear-gradient(to right, transparent, var(--gold), var(--blood2), var(--gold), transparent); opacity: 0.5; animation: jw-fadeSlideUp 1s 0.3s ease both; }
        .jw-mission-label { font-family: 'Cinzel', serif; font-size: 11px; letter-spacing: 6px; color: var(--text2); text-transform: uppercase; margin-bottom: 14px; animation: jw-fadeSlideUp 1s 0.4s ease both; }
        .jw-mission-input-wrap { position: relative; width: min(560px, 85vw); animation: jw-fadeSlideUp 1s 0.5s ease both; }
        .jw-mission-input { width: 100%; background: transparent; border: none; border-bottom: 2px solid var(--gold); color: var(--white); font-family: 'Bebas Neue', sans-serif; font-size: 28px; letter-spacing: 3px; text-align: center; padding: 12px 0; outline: none; caret-color: var(--blood2); transition: border-color 0.3s; }
        .jw-mission-input::placeholder { color: rgba(212,160,23,0.25); font-size: 22px; }
        .jw-mission-input:focus { border-bottom-color: var(--blood2); }
        .jw-input-glow { position: absolute; bottom: -2px; left: 50%; width: 0; height: 2px; background: var(--blood2); transform: translateX(-50%); transition: width 0.4s ease; box-shadow: 0 0 12px var(--blood2); }
        .jw-mission-input:focus ~ .jw-input-glow { width: 100%; }
        .jw-start-btn { margin-top: 32px; font-family: 'Bebas Neue', sans-serif; font-size: 18px; letter-spacing: 8px; color: var(--darker); background: linear-gradient(135deg, var(--gold2), var(--gold)); border: none; padding: 18px 56px; cursor: crosshair; position: relative; overflow: hidden; clip-path: polygon(8px 0%, 100% 0%, calc(100% - 8px) 100%, 0% 100%); transition: all 0.3s; animation: jw-fadeSlideUp 1s 0.6s ease both; }
        .jw-start-btn::after { content: ''; position: absolute; inset: 0; background: rgba(255,255,255,0.15); transform: translateX(-100%) skewX(-20deg); transition: transform 0.4s; }
        .jw-start-btn:hover::after { transform: translateX(100%) skewX(-20deg); }
        .jw-start-btn:hover { box-shadow: 0 0 30px rgba(245,200,66,0.5), 0 0 60px rgba(192,17,43,0.3); }
        .jw-start-btn:active { transform: scale(0.97); }
        .jw-meta-row { margin-top: 28px; font-size: 10px; letter-spacing: 4px; color: var(--text2); animation: jw-fadeSlideUp 1s 0.7s ease both; }

        .jw-focus-page { display: grid; grid-template-columns: 1fr 340px 1fr; width: 100%; height: 100%; align-items: center; }
        .jw-left-panel { grid-column: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; padding: 20px; position: relative; overflow: hidden; }
        .jw-center-panel { grid-column: 2; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 0; padding: 20px 0; position: relative; z-index: 20; }
        .jw-right-panel { grid-column: 3; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; padding: 20px; gap: 24px; }
        .jw-mh { position: fixed; top: 0; left: 0; right: 0; z-index: 50; display: flex; align-items: center; justify-content: space-between; padding: 14px 32px; background: linear-gradient(to bottom, rgba(0,0,0,0.9), transparent); }
        .jw-mh-left { font-family: 'Bebas Neue', sans-serif; font-size: 13px; letter-spacing: 5px; color: var(--gold); opacity: 0.7; }
        .jw-mh-target { font-family: 'Bebas Neue', sans-serif; font-size: 16px; letter-spacing: 3px; color: var(--blood2); text-shadow: 0 0 10px rgba(192,17,43,0.5); max-width: 300px; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .jw-mh-abort { font-family: 'Bebas Neue', sans-serif; font-size: 12px; letter-spacing: 4px; color: var(--text2); background: none; border: 1px solid rgba(122,112,96,0.3); padding: 6px 16px; cursor: crosshair; transition: all 0.3s; }
        .jw-mh-abort:hover { color: var(--blood2); border-color: var(--blood2); }
        .jw-phase-eyebrow { font-family: 'Cinzel', serif; font-size: 9px; letter-spacing: 6px; color: var(--text2); text-transform: uppercase; margin-bottom: 6px; }
        .jw-chamber-wrap { position: relative; width: 260px; height: 260px; margin: 8px 0; }
        .jw-chamber-svg { width: 100%; height: 100%; filter: drop-shadow(0 0 20px rgba(212,160,23,0.2)); }
        .jw-chamber-inner { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; }
        .jw-timer-digits { font-family: 'Bebas Neue', sans-serif; font-size: 64px; color: var(--gold2); letter-spacing: 2px; line-height: 1; text-shadow: 0 0 20px rgba(245,200,66,0.5), 0 0 40px rgba(245,200,66,0.2); }
        .jw-timer-digits.urgent { color: var(--blood2); text-shadow: 0 0 20px rgba(192,17,43,0.6), 0 0 40px rgba(192,17,43,0.3); animation: jw-urgentPulse 0.5s ease infinite; }
        @keyframes jw-urgentPulse { 0%,100%{text-shadow:0 0 20px rgba(192,17,43,0.6)} 50%{text-shadow:0 0 40px rgba(192,17,43,1), 0 0 80px rgba(192,17,43,0.5)} }
        .jw-phase-tag { font-family: 'Cinzel', serif; font-size: 9px; letter-spacing: 4px; color: var(--text2); text-transform: uppercase; }
        .jw-ctrl-row { display: flex; gap: 12px; align-items: center; margin: 14px 0 10px; }
        .jw-ctrl-btn { font-family: 'Bebas Neue', sans-serif; font-size: 15px; letter-spacing: 5px; padding: 13px 36px; border: 1px solid var(--gold); color: var(--gold); background: transparent; cursor: crosshair; position: relative; overflow: hidden; clip-path: polygon(6px 0%, 100% 0%, calc(100% - 6px) 100%, 0% 100%); transition: all 0.3s; }
        .jw-ctrl-btn::before { content: ''; position: absolute; inset: 0; background: var(--gold); transform: translateX(-101%); transition: transform 0.3s ease; }
        .jw-ctrl-btn:hover::before { transform: translateX(0); }
        .jw-ctrl-btn:hover { color: var(--darker); }
        .jw-ctrl-btn span { position: relative; z-index: 1; }
        .jw-skip-btn { font-family: 'Bebas Neue', sans-serif; font-size: 11px; letter-spacing: 3px; color: var(--text2); background: none; border: none; cursor: crosshair; padding: 6px 10px; transition: color 0.3s; }
        .jw-skip-btn:hover { color: var(--white); }
        .jw-phase-dots { display: flex; gap: 6px; margin-top: 8px; }
        .jw-phase-dot { width: 28px; height: 3px; background: var(--smoke); transition: all 0.5s ease; }
        .jw-phase-dot.done { background: var(--blood); }
        .jw-phase-dot.active { background: var(--gold2); box-shadow: 0 0 8px var(--gold2); }
        .jw-bomb-display { display: none; flex-direction: column; align-items: center; gap: 6px; }
        .jw-bomb-display.visible { display: flex; }
        .jw-bomb-digits { font-family: 'Share Tech Mono', monospace; font-size: 72px; color: #ff2020; text-shadow: 0 0 10px rgba(255,32,32,0.8), 0 0 30px rgba(255,32,32,0.5), 0 0 60px rgba(255,32,32,0.3); letter-spacing: 4px; animation: jw-bombTick 1s steps(1) infinite; }
        @keyframes jw-bombTick { 0%,99%{opacity:1} 50%{opacity:0.7} }
        .jw-bomb-wire { display: flex; gap: 8px; align-items: center; }
        .jw-wire { height: 3px; width: 40px; border-radius: 2px; }
        .jw-wire.red { background: var(--blood2); animation: jw-wirePulse 1s ease infinite; }
        .jw-wire.blue { background: #1a6aff; animation: jw-wirePulse 1s 0.3s ease infinite; }
        .jw-wire.green { background: #1a8a2a; animation: jw-wirePulse 1s 0.6s ease infinite; }
        @keyframes jw-wirePulse { 0%,100%{box-shadow: 0 0 4px currentColor; opacity: 0.8} 50%{box-shadow: 0 0 12px currentColor; opacity: 1} }
        .jw-bomb-label { font-size: 9px; letter-spacing: 5px; color: var(--blood2); opacity: 0.6; animation: jw-labelBreathe 1s ease infinite; }
        @keyframes jw-labelBreathe { 0%,100%{opacity:0.5} 50%{opacity:1} }
        .jw-anim-stage { width: min(300px, 30vw); height: min(360px, 52vh); position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; }
        .jw-phase-video { width: 100%; height: 100%; object-fit: cover; display: block; border: 1px solid rgba(212,160,23,0.15); box-shadow: 0 0 40px rgba(0,0,0,0.8), inset 0 0 0 1px rgba(212,160,23,0.1); }
        .jw-video-placeholder { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; background: rgba(6,5,8,0.92); border: 1px solid rgba(212,160,23,0.12); pointer-events: none; }
        .jw-vp-icon { font-size: 36px; opacity: 0.25; }
        .jw-vp-text { font-family: 'Share Tech Mono', monospace; font-size: 9px; letter-spacing: 3px; color: var(--text2); text-align: center; line-height: 1.8; padding: 0 20px; }
        .jw-vp-text span { display: block; color: var(--gold); opacity: 0.5; font-size: 8px; margin-top: 4px; }
        .jw-anim-stage::before, .jw-anim-stage::after { content: ''; position: absolute; width: 20px; height: 20px; border-color: rgba(212,160,23,0.4); border-style: solid; pointer-events: none; z-index: 5; }
        .jw-anim-stage::before { top: 0; left: 0; border-width: 2px 0 0 2px; }
        .jw-anim-stage::after { bottom: 0; right: 0; border-width: 0 2px 2px 0; }
        .jw-anim-label { font-family: 'Bebas Neue', sans-serif; font-size: 11px; letter-spacing: 6px; color: var(--blood2); margin-top: 10px; text-shadow: 0 0 10px rgba(192,17,43,0.6); }
        .jw-quote-area { max-width: 200px; text-align: center; margin-top: 16px; }
        .jw-q-text { font-family: 'Playfair Display', serif; font-style: italic; font-size: 13px; line-height: 1.65; color: var(--text2); }
        .jw-q-attr { font-family: 'Bebas Neue', sans-serif; font-size: 10px; letter-spacing: 4px; color: var(--gold); margin-top: 8px; opacity: 0.6; }
        .jw-timeline-card { width: 100%; max-width: 220px; }
        .jw-tc-title { font-family: 'Cinzel', serif; font-size: 9px; letter-spacing: 5px; color: var(--gold); margin-bottom: 12px; text-transform: uppercase; opacity: 0.6; }
        .jw-tc-item { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-left: 2px solid transparent; transition: all 0.4s; opacity: 0.3; }
        .jw-tc-item.t-done { opacity: 0.2; border-left-color: var(--blood); }
        .jw-tc-item.t-active { opacity: 1; border-left-color: var(--gold2); background: rgba(212,160,23,0.04); }
        .jw-tc-bullet { width: 5px; height: 5px; border-radius: 50%; background: var(--text2); flex-shrink: 0; }
        .jw-tc-item.t-active .jw-tc-bullet { background: var(--gold2); box-shadow: 0 0 8px var(--gold2); }
        .jw-tc-item.t-done .jw-tc-bullet { background: var(--blood); }
        .jw-tc-name { font-family: 'Cinzel', serif; font-size: 8px; letter-spacing: 2px; color: var(--jw-text); text-transform: uppercase; flex: 1; }
        .jw-tc-dur { font-family: 'Bebas Neue', sans-serif; font-size: 12px; letter-spacing: 2px; color: var(--text2); }
        .jw-trans-page { flex-direction: column; background: rgba(0,0,0,0.92); z-index: 100; }
        .jw-trans-inner { text-align: center; animation: jw-transIn 0.5s ease both; }
        @keyframes jw-transIn { from{opacity:0;transform:scale(0.9)} to{opacity:1;transform:scale(1)} }
        .jw-trans-code { font-family: 'Bebas Neue', sans-serif; font-size: 11px; letter-spacing: 8px; color: var(--blood2); margin-bottom: 8px; }
        .jw-trans-title { font-family: 'Bebas Neue', sans-serif; font-size: clamp(60px, 8vw, 100px); line-height: 1; color: var(--white); letter-spacing: 4px; }
        .jw-trans-sub { font-family: 'Cinzel', serif; font-size: 13px; letter-spacing: 4px; color: var(--gold); margin-top: 10px; }
        .jw-trans-divider { width: 300px; height: 1px; margin: 20px auto; background: linear-gradient(to right, transparent, var(--gold), transparent); opacity: 0.5; }
        .jw-trans-next { font-family: 'Share Tech Mono', monospace; font-size: 12px; letter-spacing: 3px; color: var(--text2); margin-bottom: 24px; }
        .jw-trans-btn { font-family: 'Bebas Neue', sans-serif; font-size: 16px; letter-spacing: 6px; padding: 16px 48px; border: 1px solid var(--gold); color: var(--gold); background: transparent; cursor: crosshair; clip-path: polygon(8px 0%, 100% 0%, calc(100% - 8px) 100%, 0% 100%); transition: all 0.3s; }
        .jw-trans-btn:hover { background: var(--gold); color: var(--darker); }
        .jw-complete-page { flex-direction: column; background: rgba(0,0,0,0.95); z-index: 150; }
        .jw-complete-inner { text-align: center; animation: jw-fadeSlideUp 0.8s ease both; }
        .jw-c-eyebrow { font-family: 'Share Tech Mono', monospace; font-size: 11px; letter-spacing: 8px; color: var(--gold); opacity: 0.5; margin-bottom: 20px; }
        .jw-c-title { font-family: 'Bebas Neue', sans-serif; font-size: clamp(70px, 10vw, 130px); line-height: 0.85; letter-spacing: 4px; color: var(--white); text-shadow: 0 0 60px rgba(212,160,23,0.3); }
        .jw-c-title span { display: block; color: var(--gold2); font-size: 0.45em; letter-spacing: 14px; }
        .jw-c-rule { width: 200px; height: 1px; margin: 24px auto; background: linear-gradient(to right, transparent, var(--gold), transparent); }
        .jw-c-mission { font-family: 'Playfair Display', serif; font-style: italic; font-size: 20px; color: var(--jw-text); margin-bottom: 8px; }
        .jw-c-stats { font-family: 'Share Tech Mono', monospace; font-size: 10px; letter-spacing: 3px; color: var(--text2); margin-bottom: 32px; }
        .jw-c-btn { font-family: 'Bebas Neue', sans-serif; font-size: 16px; letter-spacing: 6px; color: var(--darker); background: linear-gradient(135deg, var(--gold2), var(--gold)); border: none; padding: 16px 48px; cursor: crosshair; clip-path: polygon(8px 0%, 100% 0%, calc(100% - 8px) 100%, 0% 100%); transition: all 0.3s; }
        .jw-c-btn:hover { box-shadow: 0 0 30px rgba(245,200,66,0.4); }
        .jw-flash { position: absolute; inset: 0; z-index: 500; pointer-events: none; transition: opacity 0.1s; }
      `}</style>

      <canvas ref={canvasRef} className="jw-bg-canvas" />
      <div className="jw-grain" />
      <div className="jw-vignette" />
      <div className="jw-scanlines" />
      <div ref={bloodBgRef} className="jw-blood-bg" />

      {flashColor && (
        <div className="jw-flash" style={{ background: flashColor, opacity: 0.35 }} />
      )}

      {/* LANDING */}
      <div className={'jw-page jw-landing' + (page === 'landing' ? ' active' : '')}>
        <div className="jw-continental-bg">
          <svg className="jw-seal" viewBox="0 0 400 400" fill="none">
            <circle cx="200" cy="200" r="190" stroke="#c9a84c" strokeWidth="1" />
            <circle cx="200" cy="200" r="170" stroke="#c9a84c" strokeWidth="0.5" />
            <circle cx="200" cy="200" r="150" stroke="#c9a84c" strokeWidth="1" />
            <line x1="200" y1="10" x2="200" y2="50" stroke="#c9a84c" strokeWidth="2" />
            <line x1="200" y1="350" x2="200" y2="390" stroke="#c9a84c" strokeWidth="2" />
            <line x1="10" y1="200" x2="50" y2="200" stroke="#c9a84c" strokeWidth="2" />
            <line x1="350" y1="200" x2="390" y2="200" stroke="#c9a84c" strokeWidth="2" />
            <circle cx="200" cy="200" r="30" stroke="#c9a84c" strokeWidth="1" />
            <circle cx="200" cy="200" r="8" fill="#c9a84c" opacity="0.3" />
            <line x1="170" y1="200" x2="190" y2="200" stroke="#c9a84c" strokeWidth="1" />
            <line x1="210" y1="200" x2="230" y2="200" stroke="#c9a84c" strokeWidth="1" />
            <line x1="200" y1="170" x2="200" y2="190" stroke="#c9a84c" strokeWidth="1" />
            <line x1="200" y1="210" x2="200" y2="230" stroke="#c9a84c" strokeWidth="1" />
            <g stroke="#c9a84c" strokeWidth="0.5" opacity="0.6">
              <line x1="79" y1="79" x2="86" y2="86" /><line x1="321" y1="79" x2="314" y2="86" />
              <line x1="79" y1="321" x2="86" y2="314" /><line x1="321" y1="321" x2="314" y2="314" />
            </g>
            <path id="topArc" d="M 40,200 A 160,160 0 0,1 360,200" fill="none" />
            <text fontFamily="Cinzel,serif" fontSize="11" fill="#c9a84c" letterSpacing="8">
              <textPath href="#topArc" startOffset="8%">THE MAN OF FOCUS · PRODUCTIVITY SYSTEM</textPath>
            </text>
            <path id="botArc" d="M 40,200 A 160,160 0 0,0 360,200" fill="none" />
            <text fontFamily="Cinzel,serif" fontSize="11" fill="#c9a84c" letterSpacing="8">
              <textPath href="#botArc" startOffset="8%">FOCUS · DISCIPLINE · EXECUTION</textPath>
            </text>
          </svg>
        </div>
        <div className="jw-landing-inner">
          <div className="jw-badge">Tactical Productivity System</div>
          <div className="jw-hero-title"><span>THE MAN OF</span>FOCUS</div>
          <div className="jw-rule" />
          <div className="jw-mission-label">What is your target, Mr. Wick?</div>
          <div className="jw-mission-input-wrap">
            <input
              className="jw-mission-input"
              type="text"
              value={missionInput}
              onChange={e => setMissionInput(e.target.value)}
              placeholder="Eliminate the deadline..."
              maxLength={60}
              autoComplete="off"
              spellCheck="false"
            />
            <div className="jw-input-glow" />
          </div>
          <button className="jw-start-btn" onClick={startMission}>ACCEPT THE CONTRACT</button>
          <div className="jw-meta-row">10 · 50 · 10 · 50 · 10 · 50 · 20 &nbsp;·&nbsp; 7 PHASES &nbsp;·&nbsp; 3H 40M</div>
        </div>
      </div>

      {/* FOCUS */}
      <div className={'jw-page' + (page === 'focus' ? ' active' : '')}>
        <div className="jw-mh">
          <div className="jw-mh-left">CONTRACT ACTIVE</div>
          <div className="jw-mh-target">{mission.toUpperCase()}</div>
          <button className="jw-mh-abort" onClick={abortMission}>ABORT</button>
        </div>
        <div className="jw-focus-page" style={{ paddingTop: '60px' }}>
          <div className="jw-left-panel">
            <div className="jw-anim-stage">
              <video ref={videoRef} className="jw-phase-video" autoPlay muted loop playsInline style={{ display: 'none' }} />
              <div className="jw-video-placeholder" id="jw-video-placeholder">
                <div className="jw-vp-icon">🎬</div>
                <div className="jw-vp-text">
                  ADD YOUR VIDEO CLIPS HERE
                  <span>Place MP4 files in the folder.<br />See the VIDEOS array.</span>
                </div>
              </div>
            </div>
            <div className="jw-anim-label" id="jw-anim-label">STANDING BY</div>
            <div className="jw-quote-area">
              <div className="jw-q-text">{QUOTES[phase % QUOTES.length].t}</div>
              <div className="jw-q-attr">{QUOTES[phase % QUOTES.length].a}</div>
            </div>
          </div>
          <div className="jw-center-panel">
            <div className="jw-phase-eyebrow">PHASE {phase + 1} OF 7</div>
            <div style={{ display: p?.isBomb ? 'none' : 'block' }}>
              <div className="jw-chamber-wrap">
                <svg className="jw-chamber-svg" viewBox="0 0 260 260">
                  <defs>
                    <linearGradient id="gGold" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#f5c842" /><stop offset="100%" stopColor="#8b6914" />
                    </linearGradient>
                    <linearGradient id="gBlood" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#c0112b" /><stop offset="100%" stopColor="#4a0010" />
                    </linearGradient>
                    <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur" /><feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge></filter>
                  </defs>
                  <circle cx="130" cy="130" r="122" fill="#0d0d0f" stroke="#2a2a30" strokeWidth="2" />
                  <circle cx="130" cy="130" r="118" fill="none" stroke="#1a1a20" strokeWidth="1" />
                  <g id="cylinderGroup" transform={`rotate(${cylinderAngleRef.current} 130 130)`}>
                    <ellipse cx="130" cy="22" rx="12" ry="7" fill="#181820" stroke="#333" strokeWidth="1.5" />
                    <ellipse cx="130" cy="22" rx="7" ry="4" fill="#0a0a0f" /><circle cx="130" cy="22" r="2" fill="#c9a84c" opacity="0.4" />
                    <ellipse cx="130" cy="22" rx="12" ry="7" fill="#181820" stroke="#333" strokeWidth="1.5" transform="rotate(60 130 130)" />
                    <ellipse cx="130" cy="22" rx="7" ry="4" fill="#0a0a0f" transform="rotate(60 130 130)" /><circle cx="130" cy="22" r="2" fill="#c9a84c" opacity="0.4" transform="rotate(60 130 130)" />
                    <ellipse cx="130" cy="22" rx="12" ry="7" fill="#181820" stroke="#333" strokeWidth="1.5" transform="rotate(120 130 130)" />
                    <ellipse cx="130" cy="22" rx="7" ry="4" fill="#0a0a0f" transform="rotate(120 130 130)" /><circle cx="130" cy="22" r="2" fill="#c9a84c" opacity="0.4" transform="rotate(120 130 130)" />
                    <ellipse cx="130" cy="22" rx="12" ry="7" fill="#181820" stroke="#333" strokeWidth="1.5" transform="rotate(180 130 130)" />
                    <ellipse cx="130" cy="22" rx="7" ry="4" fill="#0a0a0f" transform="rotate(180 130 130)" /><circle cx="130" cy="22" r="2" fill="#c9a84c" opacity="0.4" transform="rotate(180 130 130)" />
                    <ellipse cx="130" cy="22" rx="12" ry="7" fill="#181820" stroke="#333" strokeWidth="1.5" transform="rotate(240 130 130)" />
                    <ellipse cx="130" cy="22" rx="7" ry="4" fill="#0a0a0f" transform="rotate(240 130 130)" /><circle cx="130" cy="22" r="2" fill="#c9a84c" opacity="0.4" transform="rotate(240 130 130)" />
                    <ellipse cx="130" cy="22" rx="12" ry="7" fill="#181820" stroke="#333" strokeWidth="1.5" transform="rotate(300 130 130)" />
                    <ellipse cx="130" cy="22" rx="7" ry="4" fill="#0a0a0f" transform="rotate(300 130 130)" /><circle cx="130" cy="22" r="2" fill="#c9a84c" opacity="0.4" transform="rotate(300 130 130)" />
                  </g>
                  <circle cx="130" cy="130" r="100" fill="none" stroke="#1a1a20" strokeWidth="14" />
                  <circle cx="130" cy="130" r="100" fill="none" stroke={p?.type === 'break' || p?.type === 'exfil' ? 'url(#gBlood)' : 'url(#gGold)'} strokeWidth="14" strokeLinecap="round" strokeDasharray="628.3" strokeDashoffset={628.3 * (1 - pct)} transform="rotate(-90 130 130)" filter="url(#glow)" />
                  <circle cx="130" cy="130" r="82" fill="#0a0a0c" stroke="#1e1e24" strokeWidth="1.5" />
                  <g stroke="#2a2a35" strokeWidth="1">
                    <line x1="130" y1="52" x2="130" y2="62" /><line x1="130" y1="52" x2="130" y2="62" transform="rotate(30 130 130)" />
                    <line x1="130" y1="52" x2="130" y2="62" transform="rotate(60 130 130)" /><line x1="130" y1="52" x2="130" y2="62" transform="rotate(90 130 130)" />
                    <line x1="130" y1="52" x2="130" y2="62" transform="rotate(120 130 130)" /><line x1="130" y1="52" x2="130" y2="62" transform="rotate(150 130 130)" />
                    <line x1="130" y1="52" x2="130" y2="62" transform="rotate(180 130 130)" /><line x1="130" y1="52" x2="130" y2="62" transform="rotate(210 130 130)" />
                    <line x1="130" y1="52" x2="130" y2="62" transform="rotate(240 130 130)" /><line x1="130" y1="52" x2="130" y2="62" transform="rotate(270 130 130)" />
                    <line x1="130" y1="52" x2="130" y2="62" transform="rotate(300 130 130)" /><line x1="130" y1="52" x2="130" y2="62" transform="rotate(330 130 130)" />
                  </g>
                  <circle cx="130" cy="130" r="8" fill="#1a1a22" stroke="#333" strokeWidth="1.5" />
                  <circle cx="130" cy="130" r="3" fill="#c9a84c" opacity="0.4" />
                </svg>
                <div className="jw-chamber-inner">
                  <div className={'jw-timer-digits' + (timeLeft <= 60 && timeLeft > 0 ? ' urgent' : '')}>
                    {formatTime(timeLeft)}
                  </div>
                  <div className="jw-phase-tag">{p?.name || ''}</div>
                </div>
              </div>
            </div>
            <div className={'jw-bomb-display' + (p?.isBomb ? ' visible' : '')}>
              <div className="jw-bomb-wire"><div className="jw-wire red" /><div className="jw-wire blue" /><div className="jw-wire green" /></div>
              <div className="jw-bomb-digits">{formatTime(timeLeft)}</div>
              <div className="jw-bomb-wire"><div className="jw-wire green" /><div className="jw-wire red" /><div className="jw-wire blue" /></div>
              <div className="jw-bomb-label">⬤ DETONATION SEQUENCE ACTIVE</div>
            </div>
            <div className="jw-ctrl-row">
              <button className="jw-ctrl-btn" onClick={toggleTimer}>
                <span>{running ? 'STAND DOWN' : 'ENGAGE'}</span>
              </button>
              <button className="jw-skip-btn" onClick={skipPhase}>SKIP →</button>
            </div>
            <div className="jw-phase-dots">
              {PHASES.map((_, i) => (
                <div key={i} className={'jw-phase-dot' + (i < phase ? ' done' : '') + (i === phase ? ' active' : '')} />
              ))}
            </div>
          </div>
          <div className="jw-right-panel">
            <div className="jw-timeline-card">
              <div className="jw-tc-title">Mission Timeline</div>
              {PHASES.map((ph, i) => (
                <div key={i} className={'jw-tc-item' + (i < phase ? ' t-done' : '') + (i === phase ? ' t-active' : '')}>
                  <div className="jw-tc-bullet" />
                  <div className="jw-tc-name">{ph.name}</div>
                  <div className="jw-tc-dur">{Math.floor(ph.dur / 60)}m</div>
                </div>
              ))}
            </div>
            <div className="jw-timeline-card" style={{ marginTop: '20px' }}>
              <div className="jw-tc-title" style={{ color: 'var(--blood2)', fontSize: '9px' }}>Soundtrack</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {trackPresets.map((track) => (
                  <button
                    key={track.id}
                    onClick={() => onTrackChange(activeTrack?.id === track.id ? null : track)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      padding: '6px 10px',
                      borderRadius: '2px',
                      border: '1px solid ' + (activeTrack?.id === track.id ? 'var(--gold2)' : 'rgba(212,160,23,0.12)'),
                      background: activeTrack?.id === track.id ? 'rgba(245,200,66,0.06)' : 'transparent',
                      cursor: 'crosshair',
                      fontFamily: "'Share Tech Mono', monospace",
                      fontSize: '9px',
                      letterSpacing: '1px',
                      color: activeTrack?.id === track.id ? 'var(--gold2)' : 'var(--text2)',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      transition: 'all 0.3s',
                    }}
                  >
                    <span>{track.title}</span>
                    <span style={{ fontSize: '8px', opacity: 0.7 }}>
                      {activeTrack?.id === track.id && isPlaying ? '▶' : activeTrack?.id === track.id ? '❚❚' : ''}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* TRANSITION */}
      <div className={'jw-page jw-trans-page' + (page === 'transition' ? ' active' : '')}>
        <div className="jw-trans-inner">
          <div className="jw-trans-code">{TRANS_DATA[phase]?.code || 'PHASE COMPLETE'}</div>
          <div className="jw-trans-title">
            {(TRANS_DATA[phase]?.title || 'TARGET\nELIMINATED').split('\n').map((line, i) => <span key={i}>{line}<br /></span>)}
          </div>
          <div className="jw-trans-divider" />
          <div className="jw-trans-sub">{TRANS_DATA[phase]?.sub || 'Stand down. Regroup.'}</div>
          <div className="jw-trans-next">
            NEXT: {PHASES[phase + 1]?.name || 'COMPLETE'} — {Math.floor((PHASES[phase + 1]?.dur || 0) / 60)} MIN
          </div>
          <button className="jw-trans-btn" onClick={continueToNext}>CONTINUE</button>
        </div>
      </div>

      {/* COMPLETE */}
      <div className={'jw-page jw-complete-page' + (page === 'complete' ? ' active' : '')}>
        <div className="jw-complete-inner">
          <div className="jw-c-eyebrow">CONTRACT FULFILLED</div>
          <div className="jw-c-title">MISSION<br /><span>ACCOMPLISHED</span></div>
          <div className="jw-c-rule" />
          <div className="jw-c-mission">{'"' + mission + '"'}</div>
          <div className="jw-c-stats">3H 40M · 7 PHASES · CONTRACT CLOSED</div>
          <button className="jw-c-btn" onClick={newMission}>NEW CONTRACT</button>
        </div>
      </div>
    </div>
  );
}
