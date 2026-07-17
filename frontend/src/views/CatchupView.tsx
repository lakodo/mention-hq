import {
  ActionIcon,
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Divider,
  Group,
  Loader,
  Modal,
  MultiSelect,
  NumberInput,
  Popover,
  Progress,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconExternalLink,
  IconFilterPlus,
  IconInfoCircle,
  IconPlus,
  IconSparkles,
  IconTrash,
} from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { SourceDot } from '../components/SourceDot';
import { PrStatusPill } from '../components/PrStatusPill';
import { itemLabel } from '../components/ItemLabel';
import { LINK_STATE_META, sourceMeta } from '../constants';
import { errorMessage } from '../api/client';
import {
  useBuckets,
  useCatchup,
  useConfirmLinks,
  useCreateTaskFromItem,
  useCreateTriageRule,
  useDeleteTriageRule,
  useEmojiMap,
  useMatchAllItems,
  useMatchStatus,
  useRejectLink,
  useSkippedItems,
  useStopMatching,
  useSuggestItemTasks,
  useTask,
  useTasks,
  useTriageItem,
  useTriageRules,
  useUnSkipItem,
} from '../api/hooks';
import { NoMatches } from '../components/NoMatches';
import { filterItems } from '../lib/search';
import { formatAgo } from '../lib/time';
import { useHq } from '../shell/HqContext';
import type { ItemWithLinks, Link } from '../types';

function confidenceLabel(confidence: number): string {
  return `${Math.round(confidence * 100)}% confident`;
}

interface LinkRowProps {
  link: Link;
  busy: boolean;
  onConfirm: () => void;
  onReject: () => void;
}

function TaskPreviewPopover({ taskId }: { taskId: string }) {
  const [opened, setOpened] = useState(false);
  const { data: task, isLoading } = useTask(opened ? taskId : undefined);

  return (
    <Popover
      opened={opened}
      onChange={setOpened}
      position="right"
      withArrow
      shadow="md"
      withinPortal
    >
      <Popover.Target>
        <ActionIcon
          size="xs"
          variant="subtle"
          color="gray"
          aria-label="Preview task"
          onClick={() => setOpened((o) => !o)}
        >
          <IconInfoCircle size={14} />
        </ActionIcon>
      </Popover.Target>
      <Popover.Dropdown style={{ maxWidth: 280 }}>
        {isLoading ? (
          <Text fz="xs" c="dimmed">
            Loading…
          </Text>
        ) : task ? (
          <Stack gap={4}>
            <Text fz="sm" fw={600}>
              {task.title}
            </Text>
            {task.description && (
              <Text fz="xs" c="dimmed">
                {task.description}
              </Text>
            )}
            <Group gap={6} mt={2}>
              <Badge size="xs" variant="default" radius="xl">
                {task.bucket}
              </Badge>
              <Badge size="xs" variant="light" radius="xl">
                {task.status}
              </Badge>
              <Text fz="xs" c="dimmed">
                {task.items.length} {task.items.length === 1 ? 'item' : 'items'}
              </Text>
            </Group>
          </Stack>
        ) : (
          <Text fz="xs" c="dimmed">
            Task not found.
          </Text>
        )}
      </Popover.Dropdown>
    </Popover>
  );
}

/**
 * A proposal has to be arguable, so the engine's reason and confidence are shown
 * next to the decision rather than behind it.
 */
function LinkRow({ link, busy, onConfirm, onReject }: LinkRowProps) {
  const meta = LINK_STATE_META[link.state];
  const isProposed = link.state === 'proposed';

  return (
    <Card withBorder radius="sm" p="sm" data-testid={`link-${link.state}`}>
      <Group gap={8} wrap="nowrap" align="flex-start">
        <Box style={{ flex: 1, minWidth: 0 }}>
          <Group gap={8} wrap="nowrap">
            <Badge size="sm" color={meta.color} variant="light">
              {meta.label}
            </Badge>
            <Text fz="sm" fw={600} truncate>
              {link.task.title}
            </Text>
            <Badge size="sm" variant="default" radius="xl">
              {link.task.bucket}
            </Badge>
            {isProposed && <TaskPreviewPopover taskId={link.task.id} />}
          </Group>

          {isProposed && (
            <Group gap={6} mt={6} wrap="nowrap">
              <Text fz="xs" c="dimmed">
                {link.engine ? `${link.engine} · ` : ''}
                {confidenceLabel(link.confidence)}
                {link.reason ? ` · ${link.reason}` : ''}
              </Text>
            </Group>
          )}
        </Box>

        {isProposed && (
          <Group gap={6} wrap="nowrap">
            <Button size="xs" variant="light" color="teal" disabled={busy} onClick={onConfirm}>
              Confirm
            </Button>
            <Button size="xs" variant="subtle" color="red" disabled={busy} onClick={onReject}>
              Reject
            </Button>
          </Group>
        )}
      </Group>
    </Card>
  );
}

interface CatchupCardProps {
  item: ItemWithLinks;
  taskOptions: { value: string; label: string }[];
  bucketOptions: string[];
  skipped?: boolean;
}

function CatchupCard({ item, taskOptions, bucketOptions, skipped = false }: CatchupCardProps) {
  // An item can already be attached (a confirmed link) yet still sit untriaged. Show those
  // tasks pre-selected in the attach box rather than as a separate badge, so Attach files it.
  const confirmedTaskIds = item.links.filter((l) => l.state === 'confirmed').map((l) => l.task.id);
  // Confirmed links move into the attach box as pre-selected tasks; proposed and rejected
  // links stay visible as their own rows to decide on.
  const shownLinks = item.links.filter((l) => l.state !== 'confirmed');
  const [selected, setSelected] = useState<string[]>(confirmedTaskIds);
  const [modalOpen, setModalOpen] = useState(false);
  const [title, setTitle] = useState(item.label);
  const [bucket, setBucket] = useState<string | null>(null);
  const [priority, setPriority] = useState(50);

  const { data: emojiMap = {} } = useEmojiMap();
  const confirm = useConfirmLinks();
  const reject = useRejectLink();
  const triage = useTriageItem();
  const unSkip = useUnSkipItem();
  const createTask = useCreateTaskFromItem();
  const suggest = useSuggestItemTasks();

  const busy =
    confirm.isPending ||
    reject.isPending ||
    triage.isPending ||
    unSkip.isPending ||
    createTask.isPending;
  const meta = sourceMeta(item.source);

  const fail = (error: unknown) =>
    notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });

  const askForTasks = () =>
    suggest.mutate(item.id, {
      onSuccess: (matches) => {
        if (matches.length === 0) {
          notifications.show({
            title: 'No match',
            message: 'The brain found no task this belongs to — file it yourself.',
            color: 'gray',
          });
          return;
        }
        // Pre-select the matches in the attach box so you review and confirm them.
        setSelected(matches.map((m) => m.task.id));
        notifications.show({
          title: `Suggested ${matches.length} ${matches.length === 1 ? 'task' : 'tasks'}`,
          message: matches.map((m) => `${m.task.title} — ${m.reason}`).join('\n'),
          color: 'violet',
        });
      },
      onError: fail,
    });

  const attach = (taskIds: string[]) => {
    if (taskIds.length === 0) return;
    confirm.mutate(
      { itemId: item.id, taskIds },
      {
        onSuccess: () => {
          setSelected([]);
          notifications.show({
            title: 'Attached',
            message: `Attached to ${taskIds.length} ${taskIds.length === 1 ? 'task' : 'tasks'}.`,
            color: 'teal',
          });
        },
        onError: fail,
      },
    );
  };

  const submitNewTask = () => {
    createTask.mutate(
      { itemId: item.id, title: title.trim() || item.label, bucket: bucket ?? undefined, priority },
      {
        onSuccess: (task) => {
          setModalOpen(false);
          // Stage the new task in the attach box; Attach is what files the item away.
          setSelected((prev) => [...new Set([...prev, task.id])]);
          notifications.show({
            title: 'Task created',
            message: `${task.title} — click Attach to file this item under it.`,
            color: 'teal',
          });
        },
        onError: fail,
      },
    );
  };

  return (
    <Card withBorder radius="md" p="md" data-testid="catchup-card">
      <Group gap={8} wrap="nowrap" mb={4}>
        <SourceDot source={item.source} />
        <Text fz={11} c="dimmed" fw={600} tt="uppercase" style={{ letterSpacing: '0.04em' }}>
          {meta.label}
        </Text>
        {skipped && item.triage_reason && (
          <Badge size="xs" variant="light" color="gray" radius="xl">
            {item.triage_reason}
          </Badge>
        )}
        <Text fz="xs" c="dimmed" ml="auto">
          {formatAgo(skipped ? (item.triaged_at ?? item.occurred_at) : item.occurred_at)}
        </Text>
      </Group>

      {item.url ? (
        <Anchor href={item.url} target="_blank" rel="noreferrer" fz="sm" fw={600} mb={2}>
          <Group gap={4} wrap="nowrap" component="span" style={{ display: 'inline-flex' }}>
            {itemLabel(item.label, { ...emojiMap, ...item.emoji })}
            <IconExternalLink size={12} />
          </Group>
        </Anchor>
      ) : (
        <Text fz="sm" fw={600} mb={2}>
          {itemLabel(item.label, { ...emojiMap, ...item.emoji })}
        </Text>
      )}
      {item.context && (
        <Text fz="xs" c="dimmed" mb="sm">
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

      {shownLinks.length > 0 && (
        <Stack gap={6} mb="sm">
          {shownLinks.map((link) => (
            <LinkRow
              key={`${link.task.id}:${link.state}`}
              link={link}
              busy={busy}
              onConfirm={() => attach([link.task.id])}
              onReject={() =>
                reject.mutate({ itemId: item.id, taskId: link.task.id }, { onError: fail })
              }
            />
          ))}
        </Stack>
      )}

      <Group gap={8} align="flex-end" wrap="nowrap">
        <MultiSelect
          data={taskOptions}
          value={selected}
          onChange={setSelected}
          placeholder="Attach to tasks…"
          aria-label="Attach to tasks"
          searchable
          clearable
          style={{ flex: 1, minWidth: 0 }}
          // Portalled: the card scrolls and clips, so an inline list gets cut off.
          comboboxProps={{ withinPortal: true }}
        />
        <Button size="sm" disabled={busy || selected.length === 0} onClick={() => attach(selected)}>
          Attach
        </Button>
        <Button
          size="sm"
          variant="light"
          color="violet"
          leftSection={<IconSparkles size={15} />}
          loading={suggest.isPending}
          disabled={busy}
          onClick={askForTasks}
        >
          Match
        </Button>
        <Button size="sm" variant="light" disabled={busy} onClick={() => setModalOpen(true)}>
          New task
        </Button>
        {skipped ? (
          <Button
            size="sm"
            variant="subtle"
            color="gray"
            disabled={busy}
            onClick={() =>
              unSkip.mutate(item.id, {
                onSuccess: () =>
                  notifications.show({
                    title: 'Returned to inbox',
                    message: item.label,
                    color: 'teal',
                  }),
                onError: fail,
              })
            }
          >
            Un-skip
          </Button>
        ) : (
          <Button
            size="sm"
            variant="subtle"
            color="gray"
            disabled={busy}
            onClick={() => triage.mutate({ itemId: item.id, triaged: true }, { onError: fail })}
          >
            Skip
          </Button>
        )}
      </Group>

      <Modal opened={modalOpen} onClose={() => setModalOpen(false)} title="New task from this item">
        <Stack gap="sm">
          <TextInput
            label="Title"
            value={title}
            onChange={(e) => setTitle(e.currentTarget.value)}
            data-autofocus
          />
          <Select
            label="Bucket"
            placeholder="Match on keywords"
            data={bucketOptions}
            value={bucket}
            onChange={setBucket}
            clearable
            searchable
            comboboxProps={{ withinPortal: true }}
            maxDropdownHeight={240}
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
          <Group justify="flex-end">
            <Button variant="subtle" onClick={() => setModalOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submitNewTask} loading={createTask.isPending}>
              Create
            </Button>
          </Group>
        </Stack>
      </Modal>
    </Card>
  );
}

const SOURCE_KINDS = ['pr', 'issue', 'linear', 'slack', 'branch', 'todo', 'markdown', 'dust'];

function TriageRules() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [sources, setSources] = useState<string[]>([]);
  const [condition, setCondition] = useState<'starts_with' | 'contains'>('contains');
  const [value, setValue] = useState('');

  const { data: rules } = useTriageRules();
  const create = useCreateTriageRule();
  const remove = useDeleteTriageRule();

  const fail = (error: unknown) =>
    notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });

  const add = () => {
    if (!value.trim()) return;
    create.mutate(
      { name: name.trim(), sources, condition, value: value.trim() },
      {
        onSuccess: () => {
          setName('');
          setValue('');
          setSources([]);
          notifications.show({
            title: 'Rule added',
            message: 'Matching items are skipped.',
            color: 'teal',
          });
        },
        onError: fail,
      },
    );
  };

  return (
    <>
      <Button
        size="xs"
        variant="default"
        leftSection={<IconFilterPlus size={14} />}
        onClick={() => setOpen(true)}
      >
        Triage rules{rules?.length ? ` (${rules.length})` : ''}
      </Button>
      <Modal opened={open} onClose={() => setOpen(false)} title="Triage rules" size="lg">
        <Stack gap="sm">
          <Text fz="xs" c="dimmed">
            A matching item is skipped automatically before it reaches the inbox.
          </Text>

          {rules && rules.length === 0 && (
            <Text fz="sm" c="dimmed">
              No rules yet.
            </Text>
          )}
          {rules?.map((rule) => (
            <Group key={rule.id} justify="space-between" wrap="nowrap" gap={8}>
              <Text fz="sm" truncate style={{ minWidth: 0 }}>
                <b>{rule.name}</b> — {rule.condition === 'starts_with' ? 'starts with' : 'contains'}{' '}
                “{rule.value}”
                {rule.sources.length ? ` in ${rule.sources.join(', ')}` : ' (any source)'}
              </Text>
              <ActionIcon
                variant="subtle"
                color="red"
                aria-label={`Delete rule ${rule.name}`}
                onClick={() => remove.mutate(rule.id, { onError: fail })}
              >
                <IconTrash size={14} />
              </ActionIcon>
            </Group>
          ))}

          <Divider label="Add a rule" labelPosition="left" />
          <Group grow align="flex-end">
            <Select
              label="When it"
              data={[
                { value: 'contains', label: 'contains' },
                { value: 'starts_with', label: 'starts with' },
              ]}
              value={condition}
              onChange={(v) => setCondition((v as 'starts_with' | 'contains') ?? 'contains')}
            />
            <TextInput
              label="this text"
              placeholder="New PR"
              value={value}
              onChange={(e) => setValue(e.currentTarget.value)}
              onKeyDown={(e) => e.key === 'Enter' && add()}
            />
          </Group>
          <MultiSelect
            label="In sources"
            description="Leave empty to match every source"
            data={SOURCE_KINDS}
            value={sources}
            onChange={setSources}
          />
          <TextInput
            label="Name (optional)"
            placeholder="Ignore PR-bot posts"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button
              leftSection={<IconPlus size={15} />}
              onClick={add}
              loading={create.isPending}
              disabled={!value.trim()}
            >
              Add rule
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

// Values are hours, so sub-day windows work alongside the day-scale ones.
const WINDOW_OPTIONS = [
  { value: '1', label: 'Last hour' },
  { value: '24', label: 'Last day' },
  { value: '168', label: 'Last 7 days' },
  { value: '720', label: 'Last 30 days' },
  { value: '2160', label: 'Last 90 days' },
  { value: '', label: 'All time' },
];

const DEFAULT_WINDOW = '168';

function sinceParam(hours: string): string | undefined {
  if (!hours) return undefined;
  const d = new Date();
  d.setHours(d.getHours() - Number(hours));
  return d.toISOString();
}

function MatchProgress() {
  const { data: status } = useMatchStatus();
  const stop = useStopMatching();

  if (!status?.running) return null;

  const value = status.total > 0 ? (status.done / status.total) * 100 : 0;
  return (
    <Group gap={8} wrap="nowrap" style={{ flex: 1, maxWidth: 360 }}>
      <Progress value={value} striped animated size="sm" style={{ flex: 1 }} radius="xl" />
      <Text fz="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
        {status.remaining} left
      </Text>
      <Button
        size="xs"
        variant="subtle"
        color="red"
        loading={stop.isPending}
        onClick={() => stop.mutate()}
      >
        Stop
      </Button>
    </Group>
  );
}

export function CatchupView() {
  const { query } = useHq();
  const [tab, setTab] = useState<'inbox' | 'skipped'>('inbox');
  const [window, setWindow] = useState(DEFAULT_WINDOW);
  const since = useMemo(() => sinceParam(window), [window]);

  const { data: inboxItems, isLoading: inboxLoading } = useCatchup();
  const { data: skippedItems, isLoading: skippedLoading } = useSkippedItems(since);
  const { data: tasks } = useTasks();
  const { data: buckets } = useBuckets();
  const { data: matchStatus } = useMatchStatus();
  const matchAll = useMatchAllItems();

  const fail = (error: unknown) =>
    notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });

  const handleMatchAll = () =>
    matchAll.mutate(undefined, {
      onSuccess: () =>
        notifications.show({
          title: 'Matching started',
          message: 'Working through the inbox — watch the progress bar.',
          color: 'violet',
        }),
      onError: fail,
    });

  const taskOptions = useMemo(
    () =>
      (tasks ?? []).map((task) => ({ value: task.id, label: `${task.title} · ${task.bucket}` })),
    [tasks],
  );
  const bucketOptions = useMemo(() => (buckets ?? []).map((b) => b.name), [buckets]);

  const skipped = tab === 'skipped';
  const source = skipped ? skippedItems : inboxItems;
  const isLoading = skipped ? skippedLoading : inboxLoading;
  // In the inbox, items the engine already has a guess for come first — a one-click confirm —
  // with recency order preserved within each group by the stable sort.
  const visible = useMemo(() => {
    const filtered = filterItems(source ?? [], query);
    if (skipped) return filtered;
    const hasProposal = (item: ItemWithLinks) =>
      item.links.some((link) => link.state === 'proposed') ? 0 : 1;
    return [...filtered].sort((a, b) => hasProposal(a) - hasProposal(b));
  }, [source, query, skipped]);

  const toggle = (
    <SegmentedControl
      size="xs"
      value={tab}
      onChange={(v) => setTab(v as 'inbox' | 'skipped')}
      data={[
        { value: 'inbox', label: 'Inbox' },
        { value: 'skipped', label: 'Skipped' },
      ]}
    />
  );

  return (
    <Box style={{ flex: 1, overflow: 'auto', padding: '16px 20px 20px' }}>
      <Group
        justify="space-between"
        align="center"
        px={4}
        pb={10}
        gap={8}
        style={{ maxWidth: 860 }}
      >
        <Group gap={12} align="center">
          {toggle}
          <Text fz="xs" c="dimmed">
            {visible.length} {skipped ? 'skipped' : 'to triage'}
            {query && source ? ` (of ${source.length})` : ''}
          </Text>
        </Group>
        <Group gap={8} align="center">
          {skipped ? (
            <Select
              size="xs"
              data={WINDOW_OPTIONS}
              value={window}
              onChange={(v) => setWindow(v ?? DEFAULT_WINDOW)}
              w={140}
              comboboxProps={{ withinPortal: true }}
            />
          ) : matchStatus?.running ? (
            <MatchProgress />
          ) : (
            <>
              <Button
                size="xs"
                variant="default"
                leftSection={<IconSparkles size={14} />}
                loading={matchAll.isPending}
                onClick={handleMatchAll}
              >
                Match all
              </Button>
              <TriageRules />
            </>
          )}
        </Group>
      </Group>

      {isLoading ? (
        <Center style={{ flex: 1, minHeight: 200 }}>
          <Loader />
        </Center>
      ) : !source || source.length === 0 ? (
        <Center style={{ flex: 1, minHeight: 200 }}>
          <Stack align="center" gap="xs">
            <Text fw={600}>{skipped ? 'Nothing skipped' : 'Inbox zero'}</Text>
            <Text c="dimmed" fz="sm">
              {skipped ? 'Items you skip in the inbox appear here.' : 'Nothing left to triage.'}
            </Text>
          </Stack>
        </Center>
      ) : visible.length === 0 ? (
        <NoMatches query={query} />
      ) : (
        <Stack gap="sm" style={{ maxWidth: 860 }}>
          {visible.map((item) => (
            <CatchupCard
              key={item.id}
              item={item}
              taskOptions={taskOptions}
              bucketOptions={bucketOptions}
              skipped={skipped}
            />
          ))}
        </Stack>
      )}
    </Box>
  );
}
