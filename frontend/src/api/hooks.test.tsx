import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it } from 'vitest';
import { useConfirmLinks, useRejectLink, useTriageItem, useUpdateTask } from './hooks';
import { makeTestQueryClient } from '../test/utils';
import { db } from '../test/handlers';
import {
  AUTH_TASK_ID,
  BRANCH_ITEM_ID,
  PAYMENTS_TASK_ID,
  REFUND_TASK_ID,
  SLACK_ITEM_ID,
} from '../test/fixtures';

function wrapper({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={makeTestQueryClient()}>{children}</QueryClientProvider>;
}

describe('useUpdateTask', () => {
  it('flips a task to read on the server', async () => {
    expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.unread).toBe(true);

    const { result } = renderHook(() => useUpdateTask(), { wrapper });
    result.current.mutate({ id: PAYMENTS_TASK_ID, patch: { unread: false } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.unread).toBe(false);
    expect(db.tasks.find((t) => t.id === PAYMENTS_TASK_ID)?.unread).toBe(false);
  });

  it('flips a read task back to unread', async () => {
    const { result } = renderHook(() => useUpdateTask(), { wrapper });
    result.current.mutate({ id: REFUND_TASK_ID, patch: { unread: true } });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(db.tasks.find((t) => t.id === REFUND_TASK_ID)?.unread).toBe(true);
  });

  it('rolls the optimistic update back when the server rejects it', async () => {
    // A cache entry with no observer is collected instantly at the default gcTime of 0.
    const client = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: Infinity, staleTime: Infinity },
        mutations: { retry: false },
      },
    });
    client.setQueryData(['tasks', {}], structuredClone(db.tasks));

    const { result } = renderHook(() => useUpdateTask(), {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    });
    result.current.mutate({ id: 'task:does-not-exist', patch: { unread: false } });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const cached = client.getQueryData<typeof db.tasks>(['tasks', {}]);
    expect(cached?.find((t) => t.id === PAYMENTS_TASK_ID)?.unread).toBe(true);
  });
});

describe('useConfirmLinks', () => {
  it('confirms a proposed link and triages the item out of the inbox', async () => {
    const { result } = renderHook(() => useConfirmLinks(), { wrapper });
    result.current.mutate({ itemId: SLACK_ITEM_ID, taskIds: [PAYMENTS_TASK_ID] });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const link = result.current.data?.links.find((l) => l.task.id === PAYMENTS_TASK_ID);
    expect(link?.state).toBe('confirmed');
    expect(result.current.data?.triaged).toBe(true);
  });

  it('attaches ONE item to SEVERAL tasks in a single call', async () => {
    const { result } = renderHook(() => useConfirmLinks(), { wrapper });
    result.current.mutate({
      itemId: SLACK_ITEM_ID,
      taskIds: [PAYMENTS_TASK_ID, REFUND_TASK_ID, AUTH_TASK_ID],
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const confirmed = result.current.data?.links.filter((l) => l.state === 'confirmed') ?? [];
    expect(confirmed.map((l) => l.task.id).sort()).toEqual(
      [PAYMENTS_TASK_ID, REFUND_TASK_ID, AUTH_TASK_ID].sort(),
    );
  });

  it('escapes item ids carrying colons and tildes', async () => {
    const { result } = renderHook(() => useConfirmLinks(), { wrapper });
    result.current.mutate({ itemId: BRANCH_ITEM_ID, taskIds: [AUTH_TASK_ID] });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(BRANCH_ITEM_ID);
    expect(result.current.data?.links[0]?.state).toBe('confirmed');
  });
});

describe('useRejectLink', () => {
  it('rejects a link but leaves the item in the inbox to decide on', async () => {
    const { result } = renderHook(() => useRejectLink(), { wrapper });
    result.current.mutate({ itemId: SLACK_ITEM_ID, taskId: PAYMENTS_TASK_ID });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.links[0]?.state).toBe('rejected');
    // Rejecting one proposal is not a verdict on the item itself.
    expect(result.current.data?.triaged).toBe(false);
  });
});

describe('useTriageItem', () => {
  it('skips an item out of the inbox without linking it anywhere', async () => {
    const { result } = renderHook(() => useTriageItem(), { wrapper });
    result.current.mutate({ itemId: BRANCH_ITEM_ID, triaged: true });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.triaged).toBe(true);
    expect(result.current.data?.links).toEqual([]);
  });
});
