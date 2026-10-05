// Timer visual modes. The timer UI uses one-letter codes; the API stores the
// full names (bat_focus.mode).
export const FOCUS_MODE_TO_API = {
  N: 'normal',
  F: 'flip',
  B: 'signal',
  M: 'batmobile',
};

export const FOCUS_MODE_LABELS = {
  normal: 'Normal',
  flip: 'Flip Clock',
  signal: 'Bat-Signal',
  batmobile: 'Batmobile',
  unknown: 'Unknown',
};
