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
      <div className="fixed bottom-0 left-0 right-0 z-[999] bg-bat-surface border-t border-bat-line px-4 py-2 flex items-center justify-between md:pl-72">
        <div className="flex items-center gap-3">
          <button
            onClick={onToggle}
            className="w-8 h-8 flex items-center justify-center bg-signal-self text-bat-bg rounded text-sm font-bold hover:brightness-110 transition"
          >
            {isPlaying ? '❚❚' : '▶'}
          </button>
          <div className="text-xs">
            <div className="text-ink font-semibold tracking-wide">{activeTrack.title}</div>
            <div className="text-ink-faint font-mono text-[10px]">{isPlaying ? 'PLAYING' : 'PAUSED'}</div>
          </div>
        </div>
        <div className="flex gap-1.5">
          {trackPresets.map((track) => (
            <button
              key={track.id}
              onClick={() => onTrackChange(track)}
              className={`text-[10px] px-2.5 py-1 rounded font-mono transition ${
                activeTrack.id === track.id
                  ? 'bg-signal-self/20 text-signal-self border border-signal-self/30'
                  : 'bg-bat-raised text-ink-faint border border-bat-line hover:text-ink-muted'
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
