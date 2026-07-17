import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Checkbox,
  Group,
  Loader,
  Menu,
  Modal,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import { IconArchive, IconDots, IconPlus, IconTrash } from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ReadToggle } from '../components/ReadToggle';
import { SourceDots } from '../components/SourceDot';
import { StatusPill } from '../components/StatusPill';
import { statusMeta, UNCATEGORIZED } from '../constants';
import { errorMessage } from '../api/client';
import {
  useArchiveBucket,
  useBuckets,
  useCreateBucket,
  useDeleteBucket,
  useTasks,
  useUpdateTask,
} from '../api/hooks';
import { filterTasks } from '../lib/search';
import { groupByBucket, itemCountLabel, newestItemAt, uniqueSources } from '../lib/tasks';
import { formatAgo } from '../lib/time';
import { useHq } from '../shell/HqContext';
import type { Bucket, Task } from '../types';

function AddBucket({ ghost }: { ghost?: boolean }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [keywords, setKeywords] = useState('');
  const create = useCreateBucket();

  const save = () =>
    create.mutate(
      {
        name: name.trim(),
        keywords: keywords
          .split(',')
          .map((k) => k.trim())
          .filter(Boolean),
      },
      {
        onSuccess: () => {
          setOpen(false);
          setName('');
          setKeywords('');
        },
        onError: (error) =>
          notifications.show({
            title: 'Could not add bucket',
            message: errorMessage(error),
            color: 'red',
          }),
      },
    );

  return (
    <>
      {ghost ? (
        <Button
          variant="default"
          color="gray"
          leftSection={<IconPlus size={15} />}
          onClick={() => setOpen(true)}
        >
          New bucket
        </Button>
      ) : (
        <Button leftSection={<IconPlus size={16} />} onClick={() => setOpen(true)}>
          Add a bucket
        </Button>
      )}
      <Modal opened={open} onClose={() => setOpen(false)} title="New bucket">
        <Stack gap="sm">
          <TextInput
            label="Name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            onKeyDown={(e) => e.key === 'Enter' && name.trim() && save()}
            data-autofocus
          />
          <TextInput
            label="Keywords"
            description="Comma-separated. A task matching one files itself here automatically."
            placeholder="infra, deploy, ci"
            value={keywords}
            onChange={(e) => setKeywords(e.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={save} loading={create.isPending} disabled={!name.trim()}>
              Create
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

interface TaskCardProps {
  task: Task;
  bucketNames: string[];
  onOpen: (id: string) => void;
  onToggleRead: (task: Task) => void;
  onMoveToBucket: (task: Task, bucket: string) => void;
}

function TaskCard({ task, bucketNames, onOpen, onToggleRead, onMoveToBucket }: TaskCardProps) {
  return (
    <Card
      withBorder
      radius="md"
      p="sm"
      mb="xs"
      style={{
        borderLeft: `3px solid ${statusMeta(task.status).color}`,
        opacity: task.unread ? 1 : 0.6,
      }}
    >
      {/* Only the header and title open the task. The controls row is left out on purpose:
          the bucket dropdown portals its options, and a React portal bubbles clicks up the
          component tree, so a whole-card handler would navigate on every option pick. */}
      <Box style={{ cursor: 'pointer' }} onClick={() => onOpen(task.id)}>
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
      </Box>

      <Group gap={8} wrap="nowrap">
        <StatusPill status={task.status} size="xs" />
        <Select
          size="xs"
          variant="unstyled"
          data={bucketNames}
          value={task.bucket}
          allowDeselect={false}
          style={{ flex: 1, minWidth: 0 }}
          styles={{ input: { fontSize: 11, color: 'var(--mantine-color-dimmed)', padding: 0 } }}
          onChange={(val) => val && onMoveToBucket(task, val)}
        />
        <Box>
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
  const archiveBucket = useArchiveBucket();
  const deleteBucket = useDeleteBucket();
  const [focused, setFocused] = useState<string | null>(null);

  const columns = useMemo(
    () => groupByBucket(filterTasks(tasks ?? [], query), buckets ?? []),
    [tasks, buckets, query],
  );

  const bucketNames = useMemo(
    () => [...new Set([...(buckets ?? []).map((b) => b.name), UNCATEGORIZED])],
    [buckets],
  );

  const openArchive = (bucket: Bucket) => {
    let cascade = false;
    modals.openConfirmModal({
      title: `Archive "${bucket.name}"?`,
      children: (
        <Checkbox
          label={`Also archive its ${bucket.count} task${bucket.count !== 1 ? 's' : ''}`}
          onChange={(e) => {
            cascade = e.currentTarget.checked;
          }}
        />
      ),
      labels: { confirm: 'Archive', cancel: 'Cancel' },
      onConfirm: () =>
        archiveBucket.mutate(
          { name: bucket.name, payload: { cascade_tasks: cascade } },
          {
            onSuccess: () =>
              notifications.show({ title: 'Bucket archived', message: bucket.name, color: 'teal' }),
            onError: (err) =>
              notifications.show({ title: 'Error', message: errorMessage(err), color: 'red' }),
          },
        ),
    });
  };

  const openDelete = (bucket: Bucket) => {
    let cascade = false;
    modals.openConfirmModal({
      title: `Delete "${bucket.name}"?`,
      children: (
        <Checkbox
          label={`Also delete its ${bucket.count} task${bucket.count !== 1 ? 's' : ''}`}
          onChange={(e) => {
            cascade = e.currentTarget.checked;
          }}
        />
      ),
      labels: { confirm: 'Delete', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () =>
        deleteBucket.mutate(
          { name: bucket.name, cascadeTasks: cascade },
          {
            onSuccess: () =>
              notifications.show({ title: 'Bucket deleted', message: bucket.name, color: 'teal' }),
            onError: (err) =>
              notifications.show({ title: 'Error', message: errorMessage(err), color: 'red' }),
          },
        ),
    });
  };

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
        <Stack align="center" gap="sm">
          <Text fw={600}>No buckets yet</Text>
          <Text c="dimmed" fz="sm">
            Buckets group your tasks by subject. Make your first one.
          </Text>
          <AddBucket />
        </Stack>
      </Center>
    );
  }

  const toggleRead = (task: Task) =>
    updateTask.mutate({ id: task.id, patch: { unread: !task.unread } });

  const moveToBucket = (task: Task, bucket: string) =>
    updateTask.mutate({ id: task.id, patch: { bucket } });

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
        const bucketMeta = buckets?.find((b) => b.name === column.name);

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
              style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}
            >
              <Group
                gap={8}
                style={{ flex: 1, cursor: 'pointer', minWidth: 0 }}
                wrap="nowrap"
                onClick={() => setFocused((f) => (f === column.name ? null : column.name))}
              >
                <Text fw={600} fz="sm" truncate>
                  {column.name}
                </Text>
                <Badge radius="xl" variant="filled" style={{ flexShrink: 0 }}>
                  {column.count}
                </Badge>
              </Group>

              {bucketMeta && (
                <Menu withinPortal position="bottom-end" shadow="sm">
                  <Menu.Target>
                    <ActionIcon
                      variant="subtle"
                      color="gray"
                      size="sm"
                      aria-label={`Options for ${column.name}`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <IconDots size={14} />
                    </ActionIcon>
                  </Menu.Target>
                  <Menu.Dropdown>
                    <Menu.Item
                      leftSection={<IconArchive size={14} />}
                      onClick={() => openArchive(bucketMeta)}
                    >
                      Archive bucket
                    </Menu.Item>
                    <Menu.Item
                      color="red"
                      leftSection={<IconTrash size={14} />}
                      onClick={() => openDelete(bucketMeta)}
                    >
                      Delete bucket
                    </Menu.Item>
                  </Menu.Dropdown>
                </Menu>
              )}
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
                bucketNames={bucketNames}
                onOpen={(id) => navigate(`/task/${encodeURIComponent(id)}`)}
                onToggleRead={toggleRead}
                onMoveToBucket={moveToBucket}
              />
            ))}
          </Box>
        );
      })}

      <Box style={{ flex: '0 0 200px', paddingTop: 8 }}>
        <AddBucket ghost />
      </Box>
    </Box>
  );
}
