import '@testing-library/jest-dom';

// antd 的 responsiveObserver（Form/Card/message 等组件）依赖 window.matchMedia，
// jsdom 未实现，须补齐 mock 才能渲染 antd 组件。
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});
