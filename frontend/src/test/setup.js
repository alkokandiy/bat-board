import '@testing-library/jest-dom/vitest';

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = ResizeObserverStub;
}

Element.prototype.requestFullscreen = Element.prototype.requestFullscreen || function () {
  return Promise.resolve();
};
Element.prototype.exitFullscreen = Element.prototype.exitFullscreen || function () {
  return Promise.resolve();
};
document.exitFullscreen = document.exitFullscreen || function () {
  return Promise.resolve();
};
Object.defineProperty(document, 'fullscreenElement', { value: null, configurable: true });

if (!('wakeLock' in navigator)) {
  Object.defineProperty(navigator, 'wakeLock', {
    value: {
      request: () => Promise.resolve({ release: () => {}, addEventListener: () => {} }),
    },
    configurable: true,
  });
}

window.matchMedia = window.matchMedia || (() => ({
  matches: false,
  addListener() {},
  removeListener() {},
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent() {},
}));

if (!HTMLMediaElement.prototype.play) {
  HTMLMediaElement.prototype.play = () => Promise.resolve();
  HTMLMediaElement.prototype.pause = () => {};
  HTMLMediaElement.prototype.load = () => {};
}