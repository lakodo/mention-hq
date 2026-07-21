import { Badge, Box, Button, Card, Group, Stack, Text, Title } from '@mantine/core';
import { IconArrowRight, IconChecks, IconInbox } from '@tabler/icons-react';
import { useMemo } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useCatchup, useTasks } from '../api/hooks';
import { taskPath } from '../lib/tasks';
import { useHq } from '../shell/HqContext';
import type { Task } from '../types';

function greeting(hour: number): string {
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

/** A line with some personality, keyed off how much is waiting — deterministic, so it doesn't
 *  flicker on every render. */
function quip(catchupCount: number): string {
  if (catchupCount === 0) return "Inbox zero energy. Nothing's waiting — go build something.";
  if (catchupCount <= 5) return 'A few things poked at you while you were away.';
  return "The world happened while you were heads-down. Let's triage it.";
}

function TaskRow({ task }: { task: Task }) {
  return (
    <Card
      withBorder
      radius="md"
      p="sm"
      component={Link}
      to={taskPath(task.id)}
      data-testid="welcome-task"
      style={{ textDecoration: 'none', color: 'inherit' }}
    >
      <Group gap="sm" wrap="nowrap">
        <Badge size="lg" variant="light" color="indigo" radius="sm" style={{ flexShrink: 0 }}>
          P {task.priority}
        </Badge>
        <Box style={{ flex: 1, minWidth: 0 }}>
          <Text fw={600} truncate>
            {task.title}
          </Text>
          <Group gap={8} wrap="nowrap">
            <Badge size="xs" variant="default" radius="xl">
              {task.bucket}
            </Badge>
            <Text fz="xs" c="dimmed">
              {task.items.length} {task.items.length === 1 ? 'item' : 'items'}
            </Text>
          </Group>
        </Box>
      </Group>
    </Card>
  );
}

export function WelcomeView() {
  const navigate = useNavigate();
  const { appName } = useHq();
  const { data: tasks } = useTasks();
  const { data: catchupItems } = useCatchup();

  const catchupCount = catchupItems?.length ?? 0;
  const topTasks = useMemo(
    () =>
      [...(tasks ?? [])]
        .filter((task) => !task.archived)
        .sort((a, b) => b.priority - a.priority)
        .slice(0, 5),
    [tasks],
  );

  const hour = new Date().getHours();

  return (
    <Box style={{ flex: 1, overflow: 'auto', padding: '48px 40px' }}>
      <Box style={{ maxWidth: 760, margin: '0 auto' }}>
        <Stack gap={4} mb="xl">
          <Text fz="sm" c="dimmed" fw={600} tt="uppercase" style={{ letterSpacing: '0.08em' }}>
            {greeting(hour)}
          </Text>
          <Title order={1}>{appName}</Title>
          <Text c="dimmed">{quip(catchupCount)}</Text>
        </Stack>

        {catchupCount > 0 ? (
          <Card withBorder radius="lg" p="lg" mb="xl" bg="var(--mantine-color-pink-0)">
            <Group justify="space-between" wrap="nowrap">
              <Group gap="md" wrap="nowrap">
                <IconInbox size={28} color="var(--mantine-color-pink-6)" />
                <Box>
                  <Text fw={700} fz="lg">
                    {catchupCount} {catchupCount === 1 ? 'item' : 'items'} to catch up on
                  </Text>
                  <Text fz="sm" c="dimmed">
                    Triage what came in, then get back to the work.
                  </Text>
                </Box>
              </Group>
              <Button
                color="pink"
                rightSection={<IconArrowRight size={16} />}
                onClick={() => navigate('/catchup')}
                style={{ flexShrink: 0 }}
              >
                Catch up
              </Button>
            </Group>
          </Card>
        ) : (
          <Card withBorder radius="lg" p="lg" mb="xl" bg="var(--mantine-color-teal-0)">
            <Group gap="md" wrap="nowrap">
              <IconChecks size={28} color="var(--mantine-color-teal-6)" />
              <Box>
                <Text fw={700} fz="lg">
                  You&rsquo;re all caught up
                </Text>
                <Text fz="sm" c="dimmed">
                  Nothing waiting in the inbox. Nice.
                </Text>
              </Box>
            </Group>
          </Card>
        )}

        <Group justify="space-between" align="baseline" mb="sm">
          <Title order={4}>Top priorities</Title>
          <Text component={Link} to="/task" fz="sm" c="indigo" style={{ textDecoration: 'none' }}>
            All tasks
          </Text>
        </Group>

        {topTasks.length > 0 ? (
          <Stack gap="xs">
            {topTasks.map((task) => (
              <TaskRow key={task.id} task={task} />
            ))}
          </Stack>
        ) : (
          <Text c="dimmed" fz="sm">
            No tasks yet. Promote an item from catch-up to start one.
          </Text>
        )}
      </Box>
    </Box>
  );
}
