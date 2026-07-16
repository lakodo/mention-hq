import { Badge, Box, Card, Center, Group, Loader, Stack, Text } from '@mantine/core';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ReadToggle } from '../components/ReadToggle';
import { SourceDots } from '../components/SourceDot';
import { StatusPill } from '../components/StatusPill';
import { statusMeta } from '../constants';
import { useBuckets, useTasks, useUpdateTask } from '../api/hooks';
import { filterTasks } from '../lib/search';
import { groupByBucket, itemCountLabel, newestItemAt, uniqueSources } from '../lib/tasks';
import { formatAgo } from '../lib/time';
import { useHq } from '../shell/HqContext';
import type { Task } from '../types';

interface TaskCardProps {
  task: Task;
  onOpen: (id: string) => void;
  onToggleRead: (task: Task) => void;
}

function TaskCard({ task, onOpen, onToggleRead }: TaskCardProps) {
  return (
    <Card
      withBorder
      radius="md"
      p="sm"
      mb="xs"
      onClick={() => onOpen(task.id)}
      style={{
        cursor: 'pointer',
        borderLeft: `3px solid ${statusMeta(task.status).color}`,
        opacity: task.unread ? 1 : 0.6,
      }}
    >
      <Group gap={6} mb={6} wrap="nowrap">
        <SourceDots sources={uniqueSources(task)} />
        <Text fz="xs" c="dimmed" ml={6}>
          {itemCountLabel(task)}
        </Text>
        <Text fz="xs" c="dimmed" ml="auto">
          {formatAgo(newestItemAt(task))}
        </Text>
      </Group>

      <Text fz="sm" fw={task.unread ? 700 : 400} lh={1.35} mb={8}>
        {task.title}
      </Text>

      <Group gap={8} wrap="nowrap">
        <StatusPill status={task.status} size="xs" />
        <Box ml="auto">
          <ReadToggle unread={task.unread} onToggle={() => onToggleRead(task)} />
        </Box>
      </Group>
    </Card>
  );
}

export function BoardView() {
  const navigate = useNavigate();
  const { query } = useHq();
  const { data: tasks, isLoading: tasksLoading } = useTasks();
  const { data: buckets, isLoading: bucketsLoading } = useBuckets();
  const updateTask = useUpdateTask();
  const [focused, setFocused] = useState<string | null>(null);

  const columns = useMemo(
    () => groupByBucket(filterTasks(tasks ?? [], query), buckets ?? []),
    [tasks, buckets, query],
  );

  if (tasksLoading || bucketsLoading) {
    return (
      <Center style={{ flex: 1 }}>
        <Loader />
      </Center>
    );
  }

  if (columns.length === 0) {
    return (
      <Center style={{ flex: 1 }}>
        <Stack align="center" gap="xs">
          <Text fw={600}>No buckets yet</Text>
          <Text c="dimmed" fz="sm">
            Create one in Admin to start grouping your tasks.
          </Text>
        </Stack>
      </Center>
    );
  }

  const toggleRead = (task: Task) =>
    updateTask.mutate({ id: task.id, patch: { unread: !task.unread } });

  return (
    <Box
      style={{
        flex: 1,
        overflow: 'auto',
        padding: 20,
        display: 'flex',
        gap: 16,
        alignItems: 'flex-start',
      }}
    >
      {columns.map((column) => {
        const isFocused = focused === column.name;
        const dimmed = focused !== null && !isFocused;

        return (
          <Box
            key={column.name}
            data-testid={`bucket-column-${column.name}`}
            style={{
              flex: isFocused ? '2 1 480px' : dimmed ? '0 0 220px' : '1 1 300px',
              minWidth: dimmed ? 200 : 260,
              transition: 'flex 0.25s ease, opacity 0.25s ease',
              opacity: dimmed ? 0.55 : 1,
            }}
          >
            <Group
              justify="space-between"
              px={4}
              py={8}
              mb={10}
              onClick={() => setFocused((f) => (f === column.name ? null : column.name))}
              style={{ cursor: 'pointer', borderBottom: '1px solid var(--mantine-color-gray-3)' }}
            >
              <Text fw={600} fz="sm">
                {column.name}
              </Text>
              <Badge radius="xl" variant="filled">
                {column.count}
              </Badge>
            </Group>

            {column.tasks.length === 0 && (
              <Text fz="xs" c="dimmed" px={4}>
                Nothing here.
              </Text>
            )}

            {column.tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onOpen={(id) => navigate(`/task/${encodeURIComponent(id)}`)}
                onToggleRead={toggleRead}
              />
            ))}
          </Box>
        );
      })}
    </Box>
  );
}
