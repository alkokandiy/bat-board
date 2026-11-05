// Timer visual modes. The timer UI uses one-letter codes; the API stores the
// full names (bat_focus.mode).
export const FOCUS_MODE_TO_API = {
  N: 'normal',
  F: 'flip',
  B: 'signal',
  M: 'batmobile',
};

// The way back, for restoring a session the server already knows the mode of.
// Derived rather than written out twice, so the two can never drift apart.
export const API_MODE_TO_FOCUS = Object.fromEntries(
  Object.entries(FOCUS_MODE_TO_API).map(([code, name]) => [name, code]),
);

export const FOCUS_MODE_LABELS = {
  normal: 'Normal',
  flip: 'Flip Clock',
  signal: 'Bat-Signal',
  batmobile: 'Batmobile',
  unknown: 'Unknown',
};
