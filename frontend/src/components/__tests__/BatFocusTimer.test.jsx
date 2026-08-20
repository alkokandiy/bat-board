import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import BatFocusTimer from '../BatFocusTimer';

const renderTimer = (props = {}) =>
  render(<BatFocusTimer timeLeft={1500} totalTime={1500} running={false} {...props} />);

const flipDigits = () => {
  const cards = document.querySelectorAll('div[class*="rounded-[10px]"][class*="h-[108px]"]');
  return Array.from(cards).map(
    (card) => card.querySelector('div[class*="rounded-t-[10px]"] > div').textContent
  );
};

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
    expect(document.querySelector('radialGradient[id="spotlightBeamGrad"]')).not.toBeNull();

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