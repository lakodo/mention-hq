import '@testing-library/jest-dom/vitest';
import { notifications } from '@mantine/notifications';
import { spotlight } from '@mantine/spotlight';
import { cleanup, configure } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, vi } from 'vitest';
import { resetDb } from './handlers';
import { server } from './server';

// A portalled menu/dropdown opens on a short transition timer. The whole suite runs across
// many workers, so under CPU contention that timer can outlast a short findBy wait — the menu
// is opening, just not fast enough — and a test flakes (a row menu whose "Delete item" never
// shows within the ceiling). A generous ceiling absorbs the worst contention without slowing
// the happy path: findBy resolves the instant the element appears.
configure({ asyncUtilTimeout: 8000 });

// Mantine relies on both of these; jsdom provides neither.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }),
});

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
window.ResizeObserver = ResizeObserverStub;

window.scrollTo = vi.fn();
// jsdom has no layout, so scrollIntoView is missing — the command palette calls it on selection.
Element.prototype.scrollIntoView = vi.fn();

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));

afterEach(() => {
  cleanup();
  // The notification store is a module singleton and outlives the unmounted tree;
  // left alone, toasts pile up past the display limit and later ones never show.
  notifications.clean();
  notifications.cleanQueue();
  // The spotlight store is a singleton too — a test that opens the palette would otherwise
  // leave it open, and its autofocused input steals focus from the next test.
  spotlight.close();
  server.resetHandlers();
  resetDb();
});

afterAll(() => server.close());

resetDb();
