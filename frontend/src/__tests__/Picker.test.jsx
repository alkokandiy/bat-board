import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import Picker from '../components/ui/Picker';

/**
 * The native <select> it replaced was drawn by the browser, so none of this
 * project's styling reached it — and with thirty-odd missions the list ran
 * off the bottom of the screen with no way to search it.
 */

const missions = (n) => ({
  label: 'Missions',
  options: Array.from({ length: n }, (_, i) => ({
    value: `m:${i + 1}`,
    label: `Mission number ${i + 1}`,
  })),
});

const habits = {
  label: 'Habits',
  options: [
    { value: 'h:1', label: 'Fifty press-ups' },
    { value: 'h:2', label: 'Read a page' },
  ],
};

const EMPTY = { value: '', label: '— No target (free focus) —' };

const renderPicker = (over = {}) => {
  const onChange = vi.fn();
  render(
    <Picker
      label="Focus Target"
      value=""
      onChange={onChange}
      emptyOption={EMPTY}
      groups={[missions(3), habits]}
      {...over}
    />,
  );
  return { onChange };
};

const trigger = () => screen.getByRole('button', { name: /focus target/i });

beforeEach(() => vi.clearAllMocks());

describe('Opening and choosing', () => {
  it('shows nothing until it is opened', () => {
    renderPicker();
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('opens on a click and lists the options', () => {
    renderPicker();
    fireEvent.click(trigger());
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /mission number 2/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /fifty press-ups/i })).toBeInTheDocument();
  });

  it('keeps the group headings', () => {
    renderPicker();
    fireEvent.click(trigger());
    expect(screen.getByText('Missions')).toBeInTheDocument();
    expect(screen.getByText('Habits')).toBeInTheDocument();
  });

  it('reports the chosen value and closes', () => {
    const { onChange } = renderPicker();
    fireEvent.click(trigger());
    fireEvent.click(screen.getByRole('option', { name: /read a page/i }));
    expect(onChange).toHaveBeenCalledWith('h:2');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('shows the current choice on the closed control', () => {
    renderPicker({ value: 'h:1' });
    expect(trigger()).toHaveTextContent('Fifty press-ups');
  });

  it('marks the current choice as selected', () => {
    renderPicker({ value: 'h:1' });
    fireEvent.click(trigger());
    expect(screen.getByRole('option', { name: /fifty press-ups/i }))
      .toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('option', { name: /read a page/i }))
      .toHaveAttribute('aria-selected', 'false');
  });

  it('offers the empty option so a target can be cleared', () => {
    const { onChange } = renderPicker({ value: 'h:1' });
    fireEvent.click(trigger());
    fireEvent.click(screen.getByRole('option', { name: /no target/i }));
    expect(onChange).toHaveBeenCalledWith('');
  });

  it('does nothing at all when disabled', () => {
    renderPicker({ disabled: true });
    expect(trigger()).toBeDisabled();
    fireEvent.click(trigger());
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });
});

describe('Searching, which is the point with thirty of them', () => {
  it('offers no search box for a short list', () => {
    renderPicker({ groups: [habits] });
    fireEvent.click(trigger());
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('offers one once the list is long', () => {
    renderPicker({ groups: [missions(30)] });
    fireEvent.click(trigger());
    expect(screen.getByLabelText(/search focus target/i)).toBeInTheDocument();
  });

  it('filters to what was typed', () => {
    renderPicker({ groups: [missions(30)] });
    fireEvent.click(trigger());
    fireEvent.change(screen.getByLabelText(/search focus target/i),
      { target: { value: 'number 17' } });
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(options[0]).toHaveTextContent('Mission number 17');
  });

  it('ignores case', () => {
    renderPicker({ groups: [missions(10), habits] });
    fireEvent.click(trigger());
    fireEvent.change(screen.getByLabelText(/search focus target/i),
      { target: { value: 'PRESS-UPS' } });
    expect(screen.getAllByRole('option')).toHaveLength(1);
  });

  it('says so when nothing matches, rather than showing an empty box', () => {
    renderPicker({ groups: [missions(30)] });
    fireEvent.click(trigger());
    fireEvent.change(screen.getByLabelText(/search focus target/i),
      { target: { value: 'zzzzz' } });
    expect(screen.queryAllByRole('option')).toHaveLength(0);
    expect(screen.getByText(/nothing matches/i)).toBeInTheDocument();
  });

  it('forgets the query when it is reopened', () => {
    renderPicker({ groups: [missions(30)] });
    fireEvent.click(trigger());
    fireEvent.change(screen.getByLabelText(/search focus target/i),
      { target: { value: 'number 17' } });
    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Escape' });
    fireEvent.click(trigger());
    expect(screen.getAllByRole('option').length).toBeGreaterThan(1);
  });

  it('can still pick a filtered option with the keyboard', () => {
    const { onChange } = renderPicker({ groups: [missions(30)] });
    fireEvent.click(trigger());
    const box = screen.getByLabelText(/search focus target/i);
    fireEvent.change(box, { target: { value: 'number 17' } });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('m:17');
  });
});

describe('Keyboard', () => {
  it('opens on ArrowDown', () => {
    renderPicker();
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('walks down the list and picks with Enter', () => {
    const { onChange } = renderPicker();
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' });   // opens, sits on "no target"
    const box = screen.getByRole('listbox');
    fireEvent.keyDown(box, { key: 'ArrowDown' });         // Mission 1
    fireEvent.keyDown(box, { key: 'ArrowDown' });         // Mission 2
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('m:2');
  });

  it('walks back up again', () => {
    const { onChange } = renderPicker();
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
    const box = screen.getByRole('listbox');
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    fireEvent.keyDown(box, { key: 'ArrowDown' });
    fireEvent.keyDown(box, { key: 'ArrowUp' });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('m:1');
  });

  it('stops at the ends instead of wrapping round', () => {
    const { onChange } = renderPicker();
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
    const box = screen.getByRole('listbox');
    for (let i = 0; i < 20; i += 1) fireEvent.keyDown(box, { key: 'ArrowUp' });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('');
  });

  it('End jumps to the last one', () => {
    const { onChange } = renderPicker();
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
    const box = screen.getByRole('listbox');
    fireEvent.keyDown(box, { key: 'End' });
    fireEvent.keyDown(box, { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('h:2');
  });

  it('Escape closes without choosing', () => {
    const { onChange } = renderPicker();
    fireEvent.click(trigger());
    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Escape' });
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });

  it('starts from the current choice, not the top', () => {
    const { onChange } = renderPicker({ value: 'm:2' });
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' });
    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Enter' });
    expect(onChange).toHaveBeenCalledWith('m:2');
  });
});

describe('Getting out of the way', () => {
  it('closes on a click elsewhere', () => {
    render(<div data-testid="outside">elsewhere</div>);
    renderPicker();
    fireEvent.click(trigger());
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByTestId('outside'));
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('bounds its own height instead of covering the page', () => {
    renderPicker({ groups: [missions(60)] });
    fireEvent.click(trigger());
    expect(screen.getByRole('listbox').className).toMatch(/max-h-\d+/);
    expect(screen.getByRole('listbox').className).toMatch(/overflow-y-auto/);
  });

  it('keeps a long title to one line, with the whole of it in the tooltip', () => {
    const long = 'Medium cleanup: review your posts, move the good ones to your own blog, remove the rest, and delete the account at the end.';
    renderPicker({ groups: [{ label: 'Missions', options: [{ value: 'm:9', label: long }] }] });
    fireEvent.click(trigger());
    const option = screen.getByRole('option', { name: new RegExp('Medium cleanup') });
    expect(option).toHaveAttribute('title', long);
    expect(within(option).getByText(long).className).toMatch(/truncate/);
  });

  it('says what it is, for a screen reader', () => {
    renderPicker();
    expect(trigger()).toHaveAttribute('aria-haspopup', 'listbox');
    expect(trigger()).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(trigger());
    expect(trigger()).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('listbox')).toHaveAttribute('aria-label', 'Focus Target');
  });
});

describe('Escaping the panel that clips it', () => {
  it('renders the list outside its own subtree', () => {
    // Panel has overflow-hidden, which cut the list down to the three rows
    // that happened to fit inside it. A portal is the only reliable way out
    // of an ancestor's clipping — so the list must NOT be a descendant of
    // the element the Picker was declared in.
    const { container } = render(
      <div className="overflow-hidden" data-testid="clipper">
        <Picker
          label="Focus Target"
          value=""
          onChange={() => {}}
          emptyOption={EMPTY}
          groups={[missions(3), habits]}
        />
      </div>,
    );
    fireEvent.click(screen.getByRole('button', { name: /focus target/i }));
    const list = screen.getByRole('listbox');
    expect(screen.getByTestId('clipper').contains(list)).toBe(false);
    expect(container.contains(list)).toBe(false);
    expect(document.body.contains(list)).toBe(true);
  });

  it('positions against the viewport, not the parent', () => {
    renderPicker();
    fireEvent.click(trigger());
    const panel = screen.getByRole('listbox').parentElement;
    expect(panel.style.position).toBe('fixed');
  });

  it('moves one row per keypress, not two', () => {
    // A React portal bubbles events up the REACT tree, so a key handler on
    // both the panel and the wrapper fires twice for one press.
    const { onChange } = renderPicker();
    fireEvent.keyDown(trigger(), { key: 'ArrowDown' });   // opens, on "no target"
    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'ArrowDown' });
    fireEvent.keyDown(screen.getByRole('listbox'), { key: 'Enter' });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('m:1');
  });
});
