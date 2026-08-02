import React, { useEffect, useRef } from 'react';

const trackPresets = [
  { id: 1, title: "Batmusic #1", src: "/tracks/track1.m4a" },
  { id: 2, title: "Batmusic #2", src: "/tracks/track2.m4a" },
  { id: 3, title: "Batmusic #3", src: "/tracks/track3.m4a" },
];

export { trackPresets };

export default function AudioPlayer({ activeTrack, isPlaying, onToggle = () => {}, onTrackChange = () => {}, hideUI = false }) {
  const audioRef = useRef(null);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (activeTrack && isPlaying) {
      if (audio.src !== activeTrack.src) {
        audio.src = activeTrack.src;
        audio.loop = true;
        audio.load();
        const playWhenReady = () => { audio.play().catch(() => {}); };
        audio.addEventListener('canplay', playWhenReady, { once: true });
        return () => audio.removeEventListener('canplay', playWhenReady);
      }
      audio.play().catch(() => {});
    } else {
      audio.pause();
    }
  }, [activeTrack, isPlaying]);

  if (!activeTrack) return null;
  if (hideUI) return <audio ref={audioRef} preload="auto" />;

  return (
    <>
      <audio ref={audioRef} preload="auto" />
      <div className="fixed bottom-0 left-0 right-0 z-[999] bg-dark-slate border-t border-slate-800 px-4 py-2 flex items-center justify-between md:pl-72">
        <div className="flex items-center gap-3">
          <button
            onClick={onToggle}
            className="w-8 h-8 flex items-center justify-center bg-electric-bat-yellow text-matte-obsidian rounded text-sm font-bold hover:bg-yellow-400 transition"
          >
            {isPlaying ? '❚❚' : '▶'}
          </button>
          <div className="text-xs">
            <div className="text-slate-200 font-semibold tracking-wide">{activeTrack.title}</div>
            <div className="text-slate-500 font-mono text-[10px]">{isPlaying ? 'PLAYING' : 'PAUSED'}</div>
          </div>
        </div>
        <div className="flex gap-1.5">
          {trackPresets.map((track) => (
            <button
              key={track.id}
              onClick={() => onTrackChange(track)}
              className={`text-[10px] px-2.5 py-1 rounded font-mono transition ${
                activeTrack.id === track.id
                  ? 'bg-electric-bat-yellow/20 text-electric-bat-yellow border border-electric-bat-yellow/30'
                  : 'bg-matte-obsidian text-slate-500 border border-slate-800 hover:text-slate-300'
              }`}
            >
              {track.title}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}
