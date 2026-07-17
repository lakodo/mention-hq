import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Checkbox,
  Group,
  Loader,
  Menu,
  Stack,
  Text,
  Textarea,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { modals } from '@mantine/modals';
import { notifications } from '@mantine/notifications';
import {
  IconArchive,
  IconArchiveOff,
  IconChevronLeft,
  IconChevronRight,
  IconDots,
  IconExternalLink,
  IconSearch,
  IconSparkles,
  IconTrash,
  IconX,
} from '@tabler/icons-react';
import { type MouseEvent as ReactMouseEvent, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ReadToggle } from '../components/ReadToggle';
import { SourceDot } from '../components/SourceDot';
import { StatusPill } from '../components/StatusPill';
import { SLACK_ACCENT, sourceMeta } from '../constants';
import { errorMessage } from '../api/client';
import {
  useCreateBucket,
  useDeleteTask,
  useSuggestBucket,
  useTasks,
  useUpdateTask,
} from '../api/hooks';
import { matchesSidebarQuery } from '../lib/search';
import {
  groupByTag,
  newestItemAt,
  primarySource,
  sortTasksByRecency,
  splitSlackItems,
} from '../lib/tasks';
import { formatAgo } from '../lib/time';
import type { BucketSuggestion, Item, Task } from '../types';

const DELETE_WARNING =
  'The items are kept but return to Catch-up to be triaged again. Archive instead to keep them filed.';

/** A red confirm dialog for the irreversible deletes, so the warning is unmissable. */
function confirmDelete(question: string, onConfirm: () => void) {
  modals.openConfirmModal({
    title: question,
    children: <Text size="sm">{DELETE_WARNING}</Text>,
    labels: { confirm: 'Delete', cancel: 'Cancel' },
    confirmProps: { color: 'red' },
    onConfirm,
  });
}

interface ItemCardProps {
  item: Item;
}

function ItemCard({ item }: ItemCardProps) {
  const meta = sourceMeta(item.source);

  return (
    <Card withBorder radius="sm" p="sm" data-testid="detail-item">
      <Group gap={12} align="flex-start" wrap="nowrap">
        <Box mt={5}>
          <SourceDot source={item.source} />
        </Box>
        <Box style={{ flex: 1, minWidth: 0 }}>
          <Text fz={10} c="dimmed" fw={700} tt="uppercase" style={{ letterSpacing: '0.04em' }}>
            {meta.label}
          </Text>
          {item.url ? (
            <Anchor href={item.url} target="_blank" rel="noreferrer" fz="sm" lh={1.4}>
              <Group gap={4} wrap="nowrap">
                {item.label}
                <IconExternalLink size={12} />
              </Group>
            </Anchor>
          ) : (
            <Text fz="sm" lh={1.4}>
              {item.label}
            </Text>
          )}
          {item.context && (
            <Text fz="xs" c="dimmed">
              {item.context}
            </Text>
          )}
        </Box>
        <Text fz="xs" c="dimmed" style={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
          {formatAgo(item.occurred_at)}
        </Text>
      </Group>
    </Card>
  );
}

interface SuggestionPanelProps {
  task: Task;
  suggestion: BucketSuggestion;
  onAccept: (suggestion: BucketSuggestion) => void;
  onDismiss: () => void;
  busy: boolean;
}

/** A suggestion is only ever an argument to accept or dismiss — never applied on arrival. */
function SuggestionPanel({ task, suggestion, onAccept, onDismiss, busy }: SuggestionPanelProps) {
  const alreadyThere = suggestion.bucket === task.bucket;

  return (
    <Alert color="violet" variant="light" title="Suggested bucket" mb="md">
      <Stack gap={8}>
        <Group gap={8}>
          <Badge color="violet" radius="xl">
            {suggestion.bucket}
          </Badge>
          {suggestion.is_new && (
            <Badge color="gray" variant="outline" radius="xl">
              new bucket
            </Badge>
          )}
          <Text fz="xs" c="dimmed">
            {Math.round(suggestion.confidence * 100)}% confident
          </Text>
        </Group>

        <Text fz="sm">{suggestion.reasoning}</Text>

        {suggestion.is_new && suggestion.keywords.length > 0 && (
          <Text fz="xs" c="dimmed">
            Keywords: {suggestion.keywords.join(', ')}
          </Text>
        )}

        <Group gap={8}>
          <Button
            size="xs"
            color="violet"
            disabled={busy || alreadyThere}
            onClick={() => onAccept(suggestion)}
          >
            {suggestion.is_new ? 'Create bucket and move' : 'Move to this bucket'}
          </Button>
          <Button size="xs" variant="subtle" color="gray" onClick={onDismiss}>
            Dismiss
          </Button>
          {alreadyThere && (
            <Text fz="xs" c="dimmed">
              Already in this bucket.
            </Text>
          )}
        </Group>
      </Stack>
    </Alert>
  );
}

export function TaskDetailView() {
  const { id } = useParams();
  const navigate = useNavigate();

  const [collapsed, setCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(
    () => Number(localStorage.getItem('hq:task-sidebar-width')) || 280,
  );
  const [resizing, setResizing] = useState(false);
  const [sidebarQuery, setSidebarQuery] = useState('');
  const [groupTags, setGroupTags] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [suggestion, setSuggestion] = useState<BucketSuggestion | null>(null);
  const [descDraft, setDescDraft] = useState<string | null>(null);

  const { data: tasks, isLoading } = useTasks(showArchived ? { archived: true } : {});

  const updateTask = useUpdateTask();
  const deleteTask = useDeleteTask();
  const createBucket = useCreateBucket();
  const suggest = useSuggestBucket();

  const ordered = useMemo(() => sortTasksByRecency(tasks ?? []), [tasks]);
  const filtered = useMemo(
    () => ordered.filter((task) => matchesSidebarQuery(task, sidebarQuery)),
    [ordered, sidebarQuery],
  );
  const selected = useMemo(() => ordered.find((task) => task.id === id), [ordered, id]);

  // Opening a task reads it — that's what un-bolds it on the board and in the list.
  useEffect(() => {
    if (selected?.unread) updateTask.mutate({ id: selected.id, patch: { unread: false } });
    setDescDraft(null);
    // Only when the opened task changes, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.id]);

  if (isLoading) {
    return (
      <Center style={{ flex: 1 }}>
        <Loader />
      </Center>
    );
  }

  if (ordered.length === 0) {
    return (
      <Center style={{ flex: 1 }}>
        <Text c="dimmed">No tasks yet.</Text>
      </Center>
    );
  }

  const fail = (error: unknown) =>
    notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });

  const acceptSuggestion = (accepted: BucketSuggestion) => {
    if (!selected) return;
    const move = () =>
      updateTask.mutate(
        { id: selected.id, patch: { bucket: accepted.bucket } },
        {
          onSuccess: () => {
            setSuggestion(null);
            notifications.show({
              title: 'Bucket updated',
              message: `Moved to ${accepted.bucket}.`,
              color: 'teal',
            });
          },
          onError: fail,
        },
      );

    if (!accepted.is_new) {
      move();
      return;
    }
    createBucket.mutate(
      { name: accepted.bucket, keywords: accepted.keywords },
      { onSuccess: move, onError: fail },
    );
  };

  const askForSuggestion = () => {
    if (!selected) return;
    suggest.mutate(selected.id, { onSuccess: setSuggestion, onError: fail });
  };

  const toggleArchive = () => {
    if (!selected) return;
    const archiving = !selected.archived;
    updateTask.mutate(
      { id: selected.id, patch: { archived: archiving } },
      {
        onSuccess: () => {
          notifications.show({
            title: archiving ? 'Task archived' : 'Task restored',
            message: archiving ? `${selected.title} — its items stay filed.` : selected.title,
            color: 'teal',
          });
          if (archiving) navigate('/task');
        },
        onError: fail,
      },
    );
  };

  const removeTask = () => {
    if (!selected) return;
    confirmDelete(`Delete “${selected.title}”?`, () =>
      deleteTask.mutate(selected.id, {
        onSuccess: () => {
          notifications.show({ title: 'Task deleted', message: selected.title, color: 'teal' });
          navigate('/task');
        },
        onError: fail,
      }),
    );
  };

  const setArchived = (task: Task, archiving: boolean) =>
    updateTask.mutate(
      { id: task.id, patch: { archived: archiving } },
      {
        onSuccess: () =>
          notifications.show({
            title: archiving ? 'Task archived' : 'Task restored',
            message: task.title,
            color: 'teal',
          }),
        onError: fail,
      },
    );

  const deleteOne = (task: Task) =>
    confirmDelete(`Delete “${task.title}”?`, () =>
      deleteTask.mutate(task.id, {
        onSuccess: () => {
          notifications.show({ title: 'Task deleted', message: task.title, color: 'teal' });
          if (selected?.id === task.id) navigate('/task');
        },
        onError: fail,
      }),
    );

  const toggleSelect = (id: string) =>
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const clearSelection = () => setSelectedIds(new Set());

  const plural = (n: number) => `${n} ${n === 1 ? 'task' : 'tasks'}`;

  const bulkArchive = async () => {
    const ids = [...selectedIds];
    const archiving = !showArchived;
    try {
      await Promise.all(
        ids.map((id) => updateTask.mutateAsync({ id, patch: { archived: archiving } })),
      );
      notifications.show({
        title: archiving ? 'Tasks archived' : 'Tasks restored',
        message: `${plural(ids.length)}.`,
        color: 'teal',
      });
    } catch (error) {
      fail(error);
    }
    clearSelection();
  };

  const bulkDelete = () => {
    const ids = [...selectedIds];
    confirmDelete(`Delete ${plural(ids.length)}?`, async () => {
      try {
        await Promise.all(ids.map((id) => deleteTask.mutateAsync(id)));
        notifications.show({
          title: 'Tasks deleted',
          message: `${plural(ids.length)}.`,
          color: 'teal',
        });
        if (selected && ids.includes(selected.id)) navigate('/task');
      } catch (error) {
        fail(error);
      }
      clearSelection();
    });
  };

  const { slack, other } = selected ? splitSlackItems(selected) : { slack: [], other: [] };
  const sidebarGroups = groupTags ? groupByTag(filtered) : [{ tag: '', tasks: filtered }];
  const busy = updateTask.isPending || createBucket.isPending;

  const sidebarRow = (task: Task) => {
    const source = primarySource(task);
    const active = task.id === selected?.id;
    return (
      <Group
        key={task.id}
        gap={8}
        wrap="nowrap"
        px={collapsed ? 0 : 8}
        py={6}
        mx={collapsed ? 'auto' : 8}
        justify={collapsed ? 'center' : 'flex-start'}
        style={{
          borderRadius: 6,
          background: active ? 'var(--mantine-color-gray-1)' : 'transparent',
        }}
      >
        {!collapsed && (
          <Checkbox
            size="xs"
            checked={selectedIds.has(task.id)}
            aria-label={`Select ${task.title}`}
            onChange={() => toggleSelect(task.id)}
          />
        )}
        <Group
          gap={10}
          wrap="nowrap"
          style={{ flex: 1, minWidth: 0, cursor: 'pointer' }}
          onClick={() => navigate(`/task/${encodeURIComponent(task.id)}`)}
          title={task.title}
          justify={collapsed ? 'center' : 'flex-start'}
        >
          {source ? <SourceDot source={source} /> : <Box w={8} />}
          {!collapsed && (
            <Text
              fz="sm"
              truncate
              fw={task.unread ? 700 : 400}
              c={active ? undefined : 'dimmed'}
              style={{ opacity: task.unread ? 1 : 0.65 }}
            >
              {task.title}
            </Text>
          )}
        </Group>
        {!collapsed && (
          <Menu position="bottom-end" withArrow>
            <Menu.Target>
              <ActionIcon
                variant="subtle"
                color="gray"
                size="sm"
                aria-label={`Actions for ${task.title}`}
              >
                <IconDots size={15} />
              </ActionIcon>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item
                leftSection={
                  task.archived ? <IconArchiveOff size={14} /> : <IconArchive size={14} />
                }
                onClick={() => setArchived(task, !task.archived)}
              >
                {task.archived ? 'Restore' : 'Archive'}
              </Menu.Item>
              <Menu.Item
                color="red"
                leftSection={<IconTrash size={14} />}
                onClick={() => deleteOne(task)}
              >
                Delete
              </Menu.Item>
            </Menu.Dropdown>
          </Menu>
        )}
      </Group>
    );
  };

  const startResize = (event: ReactMouseEvent) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidebarWidth;
    setResizing(true);
    document.body.style.userSelect = 'none';
    const onMove = (e: MouseEvent) =>
      setSidebarWidth(Math.min(560, Math.max(200, startWidth + e.clientX - startX)));
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      setResizing(false);
      setSidebarWidth((w) => {
        localStorage.setItem('hq:task-sidebar-width', String(w));
        return w;
      });
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  return (
    <Box style={{ flex: 1, display: 'flex', overflow: 'hidden' }}>
      <Box
        style={{
          width: collapsed ? 56 : sidebarWidth,
          flexShrink: 0,
          background: 'var(--mantine-color-body)',
          borderRight: '1px solid var(--mantine-color-gray-3)',
          display: 'flex',
          flexDirection: 'column',
          transition: resizing ? 'none' : 'width 0.18s ease',
          overflow: 'hidden',
        }}
      >
        <Group
          gap={8}
          wrap="nowrap"
          px={8}
          py={12}
          style={{ borderBottom: '1px solid var(--mantine-color-gray-3)' }}
        >
          {!collapsed && (
            <TextInput
              size="xs"
              placeholder="Search tasks…"
              aria-label="Search tasks"
              leftSection={<IconSearch size={12} />}
              value={sidebarQuery}
              onChange={(e) => setSidebarQuery(e.currentTarget.value)}
              style={{ flex: 1 }}
            />
          )}
          <Tooltip label={collapsed ? 'Expand' : 'Collapse'} withArrow>
            <ActionIcon
              variant="subtle"
              color="gray"
              aria-label="Toggle sidebar"
              onClick={() => setCollapsed((c) => !c)}
            >
              {collapsed ? <IconChevronRight size={16} /> : <IconChevronLeft size={16} />}
            </ActionIcon>
          </Tooltip>
        </Group>

        {!collapsed && selectedIds.size === 0 && (
          <Group px={12} pt={8} gap={8}>
            <Button
              size="xs"
              variant={groupTags ? 'filled' : 'default'}
              onClick={() => setGroupTags((g) => !g)}
            >
              Group by tags
            </Button>
            <Button
              size="xs"
              variant={showArchived ? 'filled' : 'default'}
              color="gray"
              leftSection={<IconArchive size={14} />}
              onClick={() => {
                setShowArchived((a) => !a);
                clearSelection();
              }}
            >
              Archived
            </Button>
          </Group>
        )}

        {!collapsed && selectedIds.size > 0 && (
          <Group px={12} pt={8} gap={8} wrap="nowrap">
            <Text fz="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
              {selectedIds.size} selected
            </Text>
            <Button
              size="xs"
              variant="light"
              color="gray"
              leftSection={showArchived ? <IconArchiveOff size={14} /> : <IconArchive size={14} />}
              loading={updateTask.isPending}
              onClick={bulkArchive}
            >
              {showArchived ? 'Restore' : 'Archive'}
            </Button>
            <Button
              size="xs"
              variant="light"
              color="red"
              leftSection={<IconTrash size={14} />}
              loading={deleteTask.isPending}
              onClick={bulkDelete}
            >
              Delete
            </Button>
            <ActionIcon
              variant="subtle"
              color="gray"
              size="sm"
              ml="auto"
              aria-label="Clear selection"
              onClick={clearSelection}
            >
              <IconX size={14} />
            </ActionIcon>
          </Group>
        )}

        <Box style={{ flex: 1, overflow: 'auto', padding: '8px 0' }}>
          {sidebarGroups.map((group) => (
            <Box key={group.tag || 'all'}>
              {groupTags && !collapsed && (
                <Text
                  fz={10}
                  fw={700}
                  c="dimmed"
                  tt="uppercase"
                  px={12}
                  pt={10}
                  pb={4}
                  style={{ letterSpacing: '0.05em' }}
                >
                  {group.tag}
                </Text>
              )}
              {group.tasks.map(sidebarRow)}
            </Box>
          ))}
        </Box>
      </Box>

      {!collapsed && (
        <Box
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize task list"
          onMouseDown={startResize}
          style={{
            width: 6,
            flexShrink: 0,
            marginLeft: -3,
            cursor: 'col-resize',
            zIndex: 1,
            background: resizing ? 'var(--mantine-color-blue-4)' : 'transparent',
          }}
        />
      )}

      <Box style={{ flex: 1, overflow: 'auto', padding: '32px 40px' }} data-testid="task-detail">
        {!selected ? (
          <Center style={{ height: '100%' }}>
            <Text c="dimmed">Select a task from the list.</Text>
          </Center>
        ) : (
          <Box style={{ maxWidth: 720 }}>
            <Group gap={8} wrap="nowrap">
              {primarySource(selected) && <SourceDot source={primarySource(selected)!} />}
              <Badge variant="default" radius="xl">
                {selected.bucket}
              </Badge>
              {selected.archived && (
                <Badge
                  variant="light"
                  color="gray"
                  radius="xl"
                  leftSection={<IconArchive size={11} />}
                >
                  Archived
                </Badge>
              )}
              <Text fz="sm" c="dimmed" ml="auto">
                {formatAgo(newestItemAt(selected))}
              </Text>
            </Group>

            <Text fz={28} fw={700} lh={1.3} my={14}>
              {selected.title}
            </Text>

            {descDraft !== null ? (
              <Textarea
                autoFocus
                autosize
                minRows={2}
                maxRows={8}
                size="sm"
                mb="md"
                value={descDraft}
                onChange={(e) => setDescDraft(e.currentTarget.value)}
                onBlur={() => {
                  const trimmed = descDraft.trim() || null;
                  updateTask.mutate({ id: selected.id, patch: { description: trimmed } });
                  setDescDraft(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setDescDraft(null);
                }}
              />
            ) : (
              <Text
                fz="sm"
                c={selected.description ? undefined : 'dimmed'}
                mb="md"
                style={{ cursor: 'text', whiteSpace: 'pre-wrap' }}
                onClick={() => setDescDraft(selected.description ?? '')}
              >
                {selected.description ?? 'Add a description…'}
              </Text>
            )}

            <Group gap={8} mb="lg">
              <StatusPill status={selected.status} />
              {selected.tags.map((tag) => (
                <Badge key={tag} variant="default" radius="xl">
                  {tag}
                </Badge>
              ))}
            </Group>

            <Group gap="md" mb="lg">
              <ReadToggle
                unread={selected.unread}
                onToggle={() =>
                  updateTask.mutate({ id: selected.id, patch: { unread: !selected.unread } })
                }
              />
              <Button
                size="xs"
                variant="light"
                color="violet"
                leftSection={<IconSparkles size={14} />}
                loading={suggest.isPending}
                onClick={askForSuggestion}
              >
                Suggest bucket
              </Button>
              <Button
                size="xs"
                variant="subtle"
                color="gray"
                leftSection={
                  selected.archived ? <IconArchiveOff size={14} /> : <IconArchive size={14} />
                }
                loading={updateTask.isPending}
                onClick={toggleArchive}
              >
                {selected.archived ? 'Restore' : 'Archive'}
              </Button>
              <Button
                size="xs"
                variant="subtle"
                color="red"
                leftSection={<IconTrash size={14} />}
                loading={deleteTask.isPending}
                onClick={removeTask}
              >
                Delete
              </Button>
            </Group>

            {suggestion && (
              <SuggestionPanel
                task={selected}
                suggestion={suggestion}
                onAccept={acceptSuggestion}
                onDismiss={() => setSuggestion(null)}
                busy={busy}
              />
            )}

            {slack.length > 0 && (
              <Box mb="lg" data-testid="slack-section">
                <Text
                  fz="xs"
                  fw={700}
                  tt="uppercase"
                  mb={8}
                  data-testid="section-heading"
                  style={{ color: SLACK_ACCENT, letterSpacing: '0.05em' }}
                >
                  Slack
                </Text>
                <Stack gap={8}>
                  {slack.map((item) => (
                    <ItemCard key={item.id} item={item} />
                  ))}
                </Stack>
              </Box>
            )}

            {other.length > 0 && (
              <Box data-testid="other-section">
                <Text
                  fz="xs"
                  fw={700}
                  c="dimmed"
                  tt="uppercase"
                  mb={8}
                  data-testid="section-heading"
                  style={{ letterSpacing: '0.05em' }}
                >
                  Other sources
                </Text>
                <Stack gap={8}>
                  {other.map((item) => (
                    <ItemCard key={item.id} item={item} />
                  ))}
                </Stack>
              </Box>
            )}

            {selected.items.length === 0 && (
              <Text c="dimmed" fz="sm">
                No items attached yet.
              </Text>
            )}
          </Box>
        )}
      </Box>
    </Box>
  );
}
