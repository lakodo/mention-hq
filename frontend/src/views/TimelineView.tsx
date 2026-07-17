import {
  ActionIcon,
  Anchor,
  Badge,
  Box,
  Button,
  Center,
  Group,
  Loader,
  Menu,
  Modal,
  MultiSelect,
  NumberInput,
  Select,
  Stack,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import {
  IconLink,
  IconPlus,
  IconSortAscending,
  IconSortDescending,
  IconTrash,
} from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SourceDot } from '../components/SourceDot';
import { PrStatusPill } from '../components/PrStatusPill';
import { itemLabel } from '../components/ItemLabel';
import { sourceMeta } from '../constants';
import { errorMessage } from '../api/client';
import {
  useConfirmLinks,
  useCreateTaskFromItem,
  useDeleteItem,
  useEmojiMap,
  useItems,
  useTasks,
} from '../api/hooks';
import { filterItems } from '../lib/search';
import { taskPath } from '../lib/tasks';
import { formatAgo } from '../lib/time';
import { useHq } from '../shell/HqContext';
import type { ItemWithLinks } from '../types';

/** The tasks an item is actually filed under — a proposal is not an attachment. */
function confirmedTasks(item: ItemWithLinks) {
  return item.links.filter((link) => link.state === 'confirmed').map((link) => link.task);
}

interface AttachModalProps {
  item: ItemWithLinks;
  taskOptions: { value: string; label: string }[];
  bucketOptions: string[];
  opened: boolean;
  onClose: () => void;
}

function AttachModal({ item, taskOptions, bucketOptions, opened, onClose }: AttachModalProps) {
  const [selected, setSelected] = useState<string[]>([]);
  const [newTitle, setNewTitle] = useState(item.label);
  const [bucket, setBucket] = useState<string | null>(null);
  const [priority, setPriority] = useState(50);
  const [view, setView] = useState<'attach' | 'new'>('attach');
  const confirm = useConfirmLinks();
  const createTask = useCreateTaskFromItem();

  const fail = (error: unknown) =>
    notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });

  const close = () => {
    setSelected([]);
    setNewTitle(item.label);
    setBucket(null);
    setPriority(50);
    setView('attach');
    onClose();
  };

  const attach = () => {
    if (selected.length === 0) return;
    confirm.mutate(
      { itemId: item.id, taskIds: selected },
      {
        onSuccess: () => {
          notifications.show({
            title: 'Attached',
            message: `Attached to ${selected.length} ${selected.length === 1 ? 'task' : 'tasks'}.`,
            color: 'teal',
          });
          close();
        },
        onError: fail,
      },
    );
  };

  const create = () => {
    createTask.mutate(
      {
        itemId: item.id,
        title: newTitle.trim() || item.label,
        bucket: bucket ?? undefined,
        priority,
      },
      {
        onSuccess: (task) => {
          notifications.show({ title: 'Task created', message: task.title, color: 'teal' });
          close();
        },
        onError: fail,
      },
    );
  };

  return (
    <Modal opened={opened} onClose={close} title={item.label} size="sm" withinPortal>
      <Stack gap="sm">
        <Group gap={8}>
          <Button
            size="xs"
            variant={view === 'attach' ? 'filled' : 'default'}
            onClick={() => setView('attach')}
          >
            Attach to task
          </Button>
          <Button
            size="xs"
            variant={view === 'new' ? 'filled' : 'default'}
            onClick={() => setView('new')}
          >
            New task
          </Button>
        </Group>

        {view === 'attach' ? (
          <>
            <MultiSelect
              data={taskOptions}
              value={selected}
              onChange={setSelected}
              placeholder="Search tasks…"
              searchable
              label="Task"
              comboboxProps={{ withinPortal: true }}
            />
            <Button
              size="sm"
              disabled={selected.length === 0}
              loading={confirm.isPending}
              onClick={attach}
            >
              Attach
            </Button>
          </>
        ) : (
          <>
            <TextInput
              label="Title"
              value={newTitle}
              onChange={(e) => setNewTitle(e.currentTarget.value)}
            />
            <Select
              label="Bucket (optional)"
              data={bucketOptions}
              value={bucket}
              onChange={setBucket}
              clearable
              comboboxProps={{ withinPortal: true }}
            />
            <NumberInput
              label="Priority"
              description="0–100, higher sorts first"
              min={0}
              max={100}
              clampBehavior="strict"
              value={priority}
              onChange={(v) => setPriority(typeof v === 'number' ? v : 50)}
            />
            <Button
              size="sm"
              loading={createTask.isPending}
              disabled={!newTitle.trim()}
              onClick={create}
            >
              Create task
            </Button>
          </>
        )}
      </Stack>
    </Modal>
  );
}

function TimelineRow({
  item,
  taskOptions,
  bucketOptions,
}: {
  item: ItemWithLinks;
  taskOptions: { value: string; label: string }[];
  bucketOptions: string[];
}) {
  const navigate = useNavigate();
  const { data: emojiMap = {} } = useEmojiMap();
  const [modalOpened, { open: openModal, close: closeModal }] = useDisclosure(false);
  const deleteItem = useDeleteItem();
  const tasks = confirmedTasks(item);
  // Triaged with nothing filed under it means it was skipped — dim it and say so.
  const skipped = item.triaged && tasks.length === 0;

  return (
    <>
      <AttachModal
        key={item.id}
        item={item}
        taskOptions={taskOptions}
        bucketOptions={bucketOptions}
        opened={modalOpened}
        onClose={closeModal}
      />
      <Group
        data-testid="timeline-row"
        gap={12}
        wrap="nowrap"
        px={16}
        py={12}
        style={{
          borderBottom: '1px solid var(--mantine-color-gray-3)',
          opacity: skipped ? 0.55 : 1,
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

        <Box style={{ flex: 1, minWidth: 0 }}>
          {item.url ? (
            <Anchor href={item.url} target="_blank" rel="noreferrer" fz="sm" truncate="end">
              {itemLabel(item.label, { ...emojiMap, ...item.emoji })}
            </Anchor>
          ) : (
            <Text fz="sm" truncate>
              {itemLabel(item.label, { ...emojiMap, ...item.emoji })}
            </Text>
          )}
          {item.context && (
            <Text fz="xs" c="dimmed" truncate>
              {item.context}
            </Text>
          )}
          {item.pr_status && (
            <PrStatusPill
              status={item.pr_status}
              reviewRequested={item.pr_review_requested}
              size="xs"
            />
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
                onClick={() => navigate(taskPath(task.id))}
                title={`${task.title} · ${task.bucket}`}
              >
                {task.title}
              </Badge>
            ))}
          </Group>
        ) : (
          <Badge variant="default" color="gray" radius="xl" style={{ flexShrink: 0 }}>
            {skipped ? 'Skipped' : 'To triage'}
          </Badge>
        )}

        <Text fz="xs" c="dimmed" style={{ width: 56, flexShrink: 0, textAlign: 'right' }}>
          {formatAgo(item.occurred_at)}
        </Text>

        <Menu withinPortal position="bottom-end" shadow="md">
          <Menu.Target>
            <Tooltip label="Attach or create task" withArrow>
              <ActionIcon variant="subtle" color="gray" size="sm" aria-label="Row actions">
                <IconPlus size={14} />
              </ActionIcon>
            </Tooltip>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item leftSection={<IconLink size={14} />} onClick={openModal}>
              Attach / new task…
            </Menu.Item>
            <Menu.Item
              color="red"
              leftSection={<IconTrash size={14} />}
              onClick={() =>
                modals.openConfirmModal({
                  title: `Delete this item?`,
                  children: (
                    <Text size="sm">
                      It is removed from HQ and any task it is on. The source is untouched.
                    </Text>
                  ),
                  labels: { confirm: 'Delete', cancel: 'Cancel' },
                  confirmProps: { color: 'red' },
                  onConfirm: () =>
                    deleteItem.mutate(item.id, {
                      onSuccess: () =>
                        notifications.show({
                          title: 'Item deleted',
                          message: item.label,
                          color: 'teal',
                        }),
                      onError: (error) =>
                        notifications.show({
                          title: 'Action failed',
                          message: errorMessage(error),
                          color: 'red',
                        }),
                    }),
                })
              }
            >
              Delete item
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>
    </>
  );
}

type Attachment = 'any' | 'filed' | 'untriaged';

export function TimelineView() {
  const { query } = useHq();
  const { data: items, isLoading } = useItems();
  const { data: allTasks } = useTasks();

  const [kinds, setKinds] = useState<string[]>([]);
  const [text, setText] = useState('');
  const [attachment, setAttachment] = useState<Attachment>('any');
  const [oldestFirst, setOldestFirst] = useState(false);

  const taskOptions = useMemo(
    () =>
      (allTasks ?? []).map((t) => ({
        value: t.id,
        label: `${t.title} · ${t.bucket}`,
      })),
    [allTasks],
  );

  const bucketOptions = useMemo(
    () => [...new Set((allTasks ?? []).map((t) => t.bucket))].sort(),
    [allTasks],
  );

  const sourceOptions = useMemo(
    () =>
      [...new Set((items ?? []).map((i) => i.source))].map((s) => ({
        value: s,
        label: sourceMeta(s).label,
      })),
    [items],
  );

  const rows = useMemo(() => {
    let list = filterItems(items ?? [], query);
    if (kinds.length) list = list.filter((i) => kinds.includes(i.source));
    const t = text.trim().toLowerCase();
    if (t)
      list = list.filter(
        (i) => i.label.toLowerCase().includes(t) || (i.context ?? '').toLowerCase().includes(t),
      );
    if (attachment === 'filed') list = list.filter((i) => confirmedTasks(i).length > 0);
    else if (attachment === 'untriaged') list = list.filter((i) => confirmedTasks(i).length === 0);
    if (oldestFirst) list = [...list].reverse();
    return list;
  }, [items, query, kinds, text, attachment, oldestFirst]);

  if (isLoading) {
    return (
      <Center style={{ flex: 1 }}>
        <Loader />
      </Center>
    );
  }

  if (!items || items.length === 0) {
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

  const filtered = kinds.length > 0 || text.trim() !== '' || attachment !== 'any';
  const clearFilters = () => {
    setKinds([]);
    setText('');
    setAttachment('any');
  };

  return (
    <Box style={{ flex: 1, overflow: 'auto', padding: '0 20px 20px' }}>
      <Group
        gap={12}
        wrap="nowrap"
        px={16}
        py={10}
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 2,
          background: 'var(--mantine-color-body)',
          borderBottom: '1px solid var(--mantine-color-gray-3)',
        }}
      >
        <MultiSelect
          size="xs"
          data={sourceOptions}
          value={kinds}
          onChange={setKinds}
          placeholder={kinds.length ? undefined : 'Source'}
          aria-label="Filter by source"
          clearable
          w={200}
          comboboxProps={{ withinPortal: true }}
        />
        <TextInput
          size="xs"
          placeholder="Filter by text…"
          aria-label="Filter by text"
          value={text}
          onChange={(e) => setText(e.currentTarget.value)}
          style={{ flex: 1 }}
        />
        <Select
          size="xs"
          data={[
            { value: 'any', label: 'Any task state' },
            { value: 'filed', label: 'On a task' },
            { value: 'untriaged', label: 'To triage' },
          ]}
          value={attachment}
          onChange={(v) => setAttachment((v as Attachment) ?? 'any')}
          aria-label="Filter by task state"
          w={150}
          comboboxProps={{ withinPortal: true }}
        />
        <Tooltip label={oldestFirst ? 'Oldest first' : 'Newest first'} withArrow>
          <ActionIcon
            variant="default"
            aria-label="Toggle sort order"
            onClick={() => setOldestFirst((o) => !o)}
          >
            {oldestFirst ? <IconSortAscending size={16} /> : <IconSortDescending size={16} />}
          </ActionIcon>
        </Tooltip>
      </Group>

      <Text fz="xs" c="dimmed" px={4} pt={10} pb={6}>
        {rows.length} {rows.length === 1 ? 'item' : 'items'}
        {oldestFirst ? ', oldest first' : ', most recent first'}
      </Text>

      {rows.length === 0 ? (
        <Center style={{ padding: '48px 0' }}>
          <Stack align="center" gap="xs">
            <Text c="dimmed" fz="sm">
              Nothing matches these filters.
            </Text>
            {filtered && (
              <Button size="xs" variant="light" onClick={clearFilters}>
                Clear filters
              </Button>
            )}
          </Stack>
        </Center>
      ) : (
        rows.map((item) => (
          <TimelineRow
            key={item.id}
            item={item}
            taskOptions={taskOptions}
            bucketOptions={bucketOptions}
          />
        ))
      )}
    </Box>
  );
}
