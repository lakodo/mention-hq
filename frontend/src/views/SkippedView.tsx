import {
  Anchor,
  Badge,
  Box,
  Button,
  Center,
  Group,
  Loader,
  Select,
  Stack,
  Text,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconExternalLink, IconInbox } from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { SourceDot } from '../components/SourceDot';
import { sourceMeta } from '../constants';
import { errorMessage } from '../api/client';
import { useSkippedItems, useUnSkipItem } from '../api/hooks';
import { formatAgo } from '../lib/time';
import type { ItemWithLinks } from '../types';

const WINDOW_OPTIONS = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: '', label: 'All time' },
];

function sinceParam(days: string): string | undefined {
  if (!days) return undefined;
  const d = new Date();
  d.setDate(d.getDate() - Number(days));
  return d.toISOString();
}

interface SkippedRowProps {
  item: ItemWithLinks;
}

function SkippedRow({ item }: SkippedRowProps) {
  const unSkip = useUnSkipItem();
  const meta = sourceMeta(item.source);

  const fail = (error: unknown) =>
    notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });

  return (
    <Group gap={12} wrap="nowrap" py={10} style={{ borderBottom: '1px solid var(--mantine-color-gray-2)' }}>
      <SourceDot source={item.source} />
      <Box style={{ flex: 1, minWidth: 0 }}>
        <Group gap={8} wrap="nowrap" mb={2}>
          <Text fz={10} c="dimmed" fw={700} tt="uppercase" style={{ letterSpacing: '0.04em', flexShrink: 0 }}>
            {meta.label}
          </Text>
          {item.triage_reason && (
            <Badge size="xs" variant="light" color="gray" radius="xl">
              {item.triage_reason}
            </Badge>
          )}
          <Text fz="xs" c="dimmed" ml="auto" style={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
            {item.triaged_at ? formatAgo(item.triaged_at) : ''}
          </Text>
        </Group>
        {item.url ? (
          <Anchor href={item.url} target="_blank" rel="noreferrer" fz="sm">
            <Group gap={4} wrap="nowrap" component="span" style={{ display: 'inline-flex' }}>
              {item.label}
              <IconExternalLink size={12} />
            </Group>
          </Anchor>
        ) : (
          <Text fz="sm">{item.label}</Text>
        )}
        {item.context && (
          <Text fz="xs" c="dimmed">
            {item.context}
          </Text>
        )}
      </Box>
      <Button
        size="xs"
        variant="subtle"
        leftSection={<IconInbox size={13} />}
        loading={unSkip.isPending}
        onClick={() =>
          unSkip.mutate(item.id, {
            onSuccess: () =>
              notifications.show({ title: 'Returned to inbox', message: item.label, color: 'teal' }),
            onError: fail,
          })
        }
      >
        Un-skip
      </Button>
    </Group>
  );
}

export function SkippedView() {
  const [window, setWindow] = useState('7');
  const since = useMemo(() => sinceParam(window), [window]);
  const { data: items, isLoading } = useSkippedItems(since);

  if (isLoading) {
    return (
      <Center style={{ flex: 1 }}>
        <Loader />
      </Center>
    );
  }

  return (
    <Box style={{ flex: 1, overflow: 'auto', padding: '16px 20px 20px' }}>
      <Group justify="space-between" px={4} pb={10} style={{ maxWidth: 860 }}>
        <Text fz="xs" c="dimmed">
          {items?.length ?? 0} skipped {(items?.length ?? 0) === 1 ? 'item' : 'items'}
        </Text>
        <Select
          size="xs"
          data={WINDOW_OPTIONS}
          value={window}
          onChange={(v) => setWindow(v ?? '7')}
          w={140}
        />
      </Group>

      {(!items || items.length === 0) ? (
        <Center style={{ flex: 1, minHeight: 200 }}>
          <Stack align="center" gap="xs">
            <Text fw={600}>Nothing skipped</Text>
            <Text c="dimmed" fz="sm">
              Items you skip in Catch-up appear here.
            </Text>
          </Stack>
        </Center>
      ) : (
        <Stack gap={0} style={{ maxWidth: 860 }}>
          {items.map((item) => (
            <SkippedRow key={item.id} item={item} />
          ))}
        </Stack>
      )}
    </Box>
  );
}
