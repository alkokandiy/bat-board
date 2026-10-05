import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import BatFocusTimer from '../BatFocusTimer';

const renderTimer = (props = {}) =>
  render(<BatFocusTimer timeLeft={1500} totalTime={1500} running={false} {...props} />);

// Each flip card exposes the digit it has settled on.
const flipDigits = () =>
  Array.from(document.querySelectorAll('[data-testid="flip-digit"]')).map((card) => card.dataset.digit);

describe('BatFocusTimer', () => {
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('renders all four modes without crashing', () => {
    renderTimer();
    expect(screen.getByText('25:00')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Flip Clock'));
    expect(screen.getByText('MISSION TIME REMAINING')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Bat-Signal'));
    expect(screen.getByTestId('bat-emblem')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Batmobile'));
    expect(document.querySelector('div[style*="height: 110px"]')).not.toBeNull();
  });

  it('caps the displayed flip-clock minutes at 99', () => {
    renderTimer({ timeLeft: 100 * 60 + 10, totalTime: 150 * 60 });
    fireEvent.click(screen.getByTitle('Flip Clock'));
    expect(flipDigits()).toEqual(['9', '9', '1', '0']);
  });

  it('FlipDigit settles to the final digit after rapid updates', async () => {
    vi.useFakeTimers();
    const { rerender } = renderTimer({ timeLeft: 600, totalTime: 600 });
    fireEvent.click(screen.getByTitle('Flip Clock'));

    await act(async () => {
      for (let i = 1; i <= 59; i++) {
        rerender(<BatFocusTimer timeLeft={600 - i} totalTime={600} running={false} />);
      }
    });
    await act(async () => {
      vi.advanceTimersByTime(60000);
    });
    rerender(<BatFocusTimer timeLeft={540} totalTime={600} running={false} />);
    await act(async () => {
      vi.advanceTimersByTime(60000);
    });

    expect(flipDigits()).toEqual(['0', '9', '0', '0']);
  });

  it('enterFocus tolerates fullscreen rejection and still starts the session', async () => {
    const onToggleRunning = vi.fn();
    const onFocusModeChange = vi.fn();
    Element.prototype.requestFullscreen = () => Promise.reject(new Error('denied'));

    renderTimer({ onToggleRunning, onFocusModeChange });
    await act(async () => {
      fireEvent.click(screen.getByText('ENTER FOCUS'));
    });

    expect(onToggleRunning).toHaveBeenCalledTimes(1);
    expect(onFocusModeChange).toHaveBeenCalledWith(true);
    expect(screen.getByText('✕ EXIT FOCUS')).toBeInTheDocument();
  });

  it('native fullscreen exit (Esc) does NOT exit focus mode; EXIT FOCUS does, without stopping the timer', () => {
    const onToggleRunning = vi.fn();
    const onFocusModeChange = vi.fn();

    renderTimer({
      initialFocusActive: true,
      running: true,
      onToggleRunning,
      onFocusModeChange,
    });
    expect(screen.getByText('✕ EXIT FOCUS')).toBeInTheDocument();

    act(() => {
      Object.defineProperty(document, 'fullscreenElement', { value: null, configurable: true });
      document.dispatchEvent(new Event('fullscreenchange'));
    });
    expect(screen.getByText('✕ EXIT FOCUS')).toBeInTheDocument();
    expect(onFocusModeChange).not.toHaveBeenCalled();

    act(() => {
      fireEvent.click(screen.getByText('✕ EXIT FOCUS'));
    });
    expect(onFocusModeChange).toHaveBeenCalledWith(false);
    expect(onToggleRunning).not.toHaveBeenCalled();
    expect(screen.getByText('ENTER FOCUS')).toBeInTheDocument();
  });
});
describe('timer visuals', () => {
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = '';
  });

  it('flip digit: flaps for a change, then settles; both faces are rendered during the flip', async () => {
    vi.useFakeTimers();
    const { rerender } = renderTimer({ timeLeft: 600, totalTime: 600 });
    fireEvent.click(screen.getByTitle('Flip Clock'));
    expect(flipDigits()).toEqual(['1', '0', '0', '0']);

    await act(async () => {
      rerender(<BatFocusTimer timeLeft={599} totalTime={600} running={false} />);
    });
    // Mid-flip: the old digit is still the settled one; the new one is on the flap's back.
    const card = document.querySelectorAll('[data-testid="flip-digit"]')[3];
    expect(card.dataset.digit).toBe('0');
    expect(card.textContent).toContain('9');

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(flipDigits()).toEqual(['0', '9', '5', '9']);
  });

  it('flip digit: no animation with prefers-reduced-motion', async () => {
    vi.useFakeTimers();
    window.matchMedia = vi.fn().mockReturnValue({ matches: true });
    const { rerender } = renderTimer({ timeLeft: 600, totalTime: 600 });
    fireEvent.click(screen.getByTitle('Flip Clock'));
    await act(async () => {
      rerender(<BatFocusTimer timeLeft={599} totalTime={600} running={false} />);
    });
    expect(flipDigits()).toEqual(['0', '9', '5', '9']);
    delete window.matchMedia;
  });

  it('bat emblem fills from the bottom with progress and keeps its outline', () => {
    renderTimer({ timeLeft: 750, totalTime: 1500 }); // 50% elapsed
    fireEvent.click(screen.getByTitle('Bat-Signal'));
    const emblem = screen.getByTestId('bat-emblem');
    expect(emblem.getAttribute('aria-label')).toContain('50%');
    const clipRect = emblem.querySelector('clipPath rect');
    expect(Number(clipRect.getAttribute('y'))).toBeCloseTo(165, 0); // halfway up a 330-high emblem
    expect(emblem.querySelectorAll('use').length).toBe(2); // unlit + lit layers share one path
  });

  it('batmobile: shows the 2D car while 3D loads and when WebGL is unavailable', async () => {
    renderTimer();
    fireEvent.click(screen.getByTitle('Batmobile'));
    // Immediately: 2D track (Suspense fallback).
    expect(document.querySelector('div[style*="height: 110px"]')).not.toBeNull();
    // jsdom has no WebGL: once the 3D chunk loads it reports "unsupported" and the 2D car stays.
    await act(async () => {
      await new Promise((r) => setTimeout(r, 100));
    });
    expect(document.querySelector('div[style*="height: 110px"]')).not.toBeNull();
    expect(screen.queryByTestId('batmobile-3d')).toBeNull();
  });
});
