import { Badge, Box, Center, Group, Loader, Stack, Text } from '@mantine/core';
import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { ReadToggle } from '../components/ReadToggle';
import { SourceDot } from '../components/SourceDot';
import { StatusPill } from '../components/StatusPill';
import { sourceMeta } from '../constants';
import { useTasks, useUpdateTask } from '../api/hooks';
import { filterTasks } from '../lib/search';
import { flattenItems } from '../lib/tasks';
import { formatAgo } from '../lib/time';
import { useHq } from '../shell/HqContext';
import type { Task } from '../types';

export function TimelineView() {
  const navigate = useNavigate();
  const { query } = useHq();
  const { data: tasks, isLoading } = useTasks();
  const updateTask = useUpdateTask();

  const rows = useMemo(() => flattenItems(filterTasks(tasks ?? [], query)), [tasks, query]);

  if (isLoading) {
    return (
      <Center style={{ flex: 1 }}>
        <Loader />
      </Center>
    );
  }

  const toggleRead = (task: Task) =>
    updateTask.mutate({ id: task.id, patch: { unread: !task.unread } });

  if (rows.length === 0) {
    return (
      <Center style={{ flex: 1 }}>
        <Stack align="center" gap="xs">
          <Text fw={600}>Nothing on the timeline</Text>
          <Text c="dimmed" fz="sm">
            Sync a source to pull in items.
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

      {rows.map(({ key, task, item }) => (
        <Group
          key={key}
          data-testid="timeline-row"
          gap={12}
          wrap="nowrap"
          px={16}
          py={12}
          onClick={() => navigate(`/task/${encodeURIComponent(task.id)}`)}
          style={{
            borderBottom: '1px solid var(--mantine-color-gray-3)',
            cursor: 'pointer',
            background: task.unread ? 'var(--mantine-color-body)' : 'transparent',
          }}
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
          <Badge variant="default" radius="xl" style={{ flexShrink: 0 }}>
            {task.bucket}
          </Badge>

          <Box style={{ flex: 1, minWidth: 0 }}>
            <Text fz="sm" fw={task.unread ? 700 : 400} truncate>
              {task.title}
            </Text>
            <Text fz="xs" c="dimmed" truncate>
              {item.label}
            </Text>
          </Box>

          <StatusPill status={task.status} size="xs" />
          <Text fz="xs" c="dimmed" style={{ width: 56, flexShrink: 0, textAlign: 'right' }}>
            {formatAgo(item.occurred_at)}
          </Text>
          <ReadToggle unread={task.unread} onToggle={() => toggleRead(task)} />
        </Group>
      ))}
    </Box>
  );
}
