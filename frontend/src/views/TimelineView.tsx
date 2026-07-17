import { Anchor, Badge, Box, Center, Group, Loader, Stack, Text } from '@mantine/core';
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { SourceDot } from '../components/SourceDot';
import { sourceMeta } from '../constants';
import { useItems } from '../api/hooks';
import { filterItems } from '../lib/search';
import { formatAgo } from '../lib/time';
import { useHq } from '../shell/HqContext';
import type { ItemWithLinks } from '../types';

/** The tasks an item is actually filed under — a proposal is not an attachment. */
function confirmedTasks(item: ItemWithLinks) {
  return item.links.filter((link) => link.state === 'confirmed').map((link) => link.task);
}

export function TimelineView() {
  const navigate = useNavigate();
  const { query } = useHq();
  const { data: items, isLoading } = useItems();

  const rows = useMemo(() => filterItems(items ?? [], query), [items, query]);

  if (isLoading) {
    return (
      <Center style={{ flex: 1 }}>
        <Loader />
      </Center>
    );
  }

  if (rows.length === 0) {
    return (
      <Center style={{ flex: 1 }}>
        <Stack align="center" gap="xs">
          <Text fw={600}>Nothing on the timeline</Text>
          <Text c="dimmed" fz="sm">
            {items && items.length > 0
              ? `No items match “${query}”.`
              : 'Sync a source to pull in items.'}
          </Text>
        </Stack>
      </Center>
    );
  }

  return (
    <Box style={{ flex: 1, overflow: 'auto', padding: '0 20px 20px' }}>
      <Text fz="xs" c="dimmed" px={4} pt={14} pb={6}>
        {rows.length} {rows.length === 1 ? 'item' : 'items'}, most recent first
      </Text>

      {rows.map((item) => {
        const tasks = confirmedTasks(item);
        return (
          <Group
            key={item.id}
            data-testid="timeline-row"
            gap={12}
            wrap="nowrap"
            px={16}
            py={12}
            style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}
          >
            <SourceDot source={item.source} />
            <Text
              fz={11}
              c="dimmed"
              fw={600}
              tt="uppercase"
              style={{ width: 64, flexShrink: 0, letterSpacing: '0.04em' }}
            >
              {sourceMeta(item.source).label}
            </Text>

            <Box style={{ flex: 1, minWidth: 0 }}>
              {item.url ? (
                <Anchor href={item.url} target="_blank" rel="noreferrer" fz="sm" truncate="end">
                  {item.label}
                </Anchor>
              ) : (
                <Text fz="sm" truncate>
                  {item.label}
                </Text>
              )}
              {item.context && (
                <Text fz="xs" c="dimmed" truncate>
                  {item.context}
                </Text>
              )}
            </Box>

            {tasks.length > 0 ? (
              <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
                {tasks.map((task) => (
                  <Badge
                    key={task.id}
                    variant="light"
                    radius="xl"
                    style={{ cursor: 'pointer' }}
                    onClick={() => navigate(`/task/${encodeURIComponent(task.id)}`)}
                    title={`${task.title} · ${task.bucket}`}
                  >
                    {task.title}
                  </Badge>
                ))}
              </Group>
            ) : (
              <Badge variant="default" color="gray" radius="xl" style={{ flexShrink: 0 }}>
                {item.triaged ? 'No task' : 'To triage'}
              </Badge>
            )}

            <Text fz="xs" c="dimmed" style={{ width: 56, flexShrink: 0, textAlign: 'right' }}>
              {formatAgo(item.occurred_at)}
            </Text>
          </Group>
        );
      })}
    </Box>
  );
}
