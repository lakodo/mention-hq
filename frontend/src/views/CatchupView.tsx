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
  Select,
  Stack,
  Text,
  TextInput,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconExternalLink,
  IconFilterPlus,
  IconPlus,
  IconSparkles,
  IconTrash,
} from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { SourceDot } from '../components/SourceDot';
import { PrStatusPill } from '../components/PrStatusPill';
import { LINK_STATE_META, sourceMeta } from '../constants';
import { errorMessage } from '../api/client';
import {
  useBuckets,
  useCatchup,
  useConfirmLinks,
  useCreateTaskFromItem,
  useCreateTriageRule,
  useDeleteTriageRule,
  useMatchAllItems,
  useRejectLink,
  useSuggestItemTasks,
  useTasks,
  useTriageItem,
  useTriageRules,
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
}

function CatchupCard({ item, taskOptions, bucketOptions }: CatchupCardProps) {
  const [selected, setSelected] = useState<string[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [title, setTitle] = useState(item.label);
  const [bucket, setBucket] = useState<string | null>(null);

  const confirm = useConfirmLinks();
  const reject = useRejectLink();
  const triage = useTriageItem();
  const createTask = useCreateTaskFromItem();
  const suggest = useSuggestItemTasks();

  const busy = confirm.isPending || reject.isPending || triage.isPending || createTask.isPending;
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
      { itemId: item.id, title: title.trim() || item.label, bucket: bucket ?? undefined },
      {
        onSuccess: (task) => {
          setModalOpen(false);
          notifications.show({ title: 'Task created', message: task.title, color: 'teal' });
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
        <Text fz="xs" c="dimmed" ml="auto">
          {formatAgo(item.occurred_at)}
        </Text>
      </Group>

      {item.url ? (
        <Anchor href={item.url} target="_blank" rel="noreferrer" fz="sm" fw={600} mb={2}>
          <Group gap={4} wrap="nowrap" component="span" style={{ display: 'inline-flex' }}>
            {item.label}
            <IconExternalLink size={12} />
          </Group>
        </Anchor>
      ) : (
        <Text fz="sm" fw={600} mb={2}>
          {item.label}
        </Text>
      )}
      {item.context && (
        <Text fz="xs" c="dimmed" mb="sm">
          {item.context}
        </Text>
      )}
      {item.pr_status && <PrStatusPill status={item.pr_status} size="xs" />}

      {item.links.length > 0 && (
        <Stack gap={6} mb="sm">
          {item.links.map((link) => (
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
        <Button
          size="sm"
          variant="subtle"
          color="gray"
          disabled={busy}
          onClick={() => triage.mutate({ itemId: item.id, triaged: true }, { onError: fail })}
        >
          Skip
        </Button>
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

export function CatchupView() {
  const { query } = useHq();
  const { data: items, isLoading } = useCatchup();
  const { data: tasks } = useTasks();
  const { data: buckets } = useBuckets();
  const matchAll = useMatchAllItems();
  const { runSync, syncing } = useHq();

  const fail = (error: unknown) =>
    notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });

  const handleMatchAll = () =>
    matchAll.mutate(undefined, {
      onSuccess: () => {
        notifications.show({
          title: 'Re-matching queued',
          message: 'Items will be matched on the next sync.',
          color: 'violet',
        });
        runSync();
      },
      onError: fail,
    });

  const taskOptions = useMemo(
    () =>
      (tasks ?? []).map((task) => ({ value: task.id, label: `${task.title} · ${task.bucket}` })),
    [tasks],
  );
  const bucketOptions = useMemo(() => (buckets ?? []).map((b) => b.name), [buckets]);
  // Items the engine already has a guess for come first — they're a one-click confirm — with
  // recency order preserved within each group by the stable sort.
  const visible = useMemo(() => {
    const hasProposal = (item: ItemWithLinks) =>
      item.links.some((link) => link.state === 'proposed') ? 0 : 1;
    return [...filterItems(items ?? [], query)].sort((a, b) => hasProposal(a) - hasProposal(b));
  }, [items, query]);

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
          <Text fw={600}>Inbox zero</Text>
          <Text c="dimmed" fz="sm">
            Nothing left to triage.
          </Text>
        </Stack>
      </Center>
    );
  }

  if (visible.length === 0) {
    return <NoMatches query={query} />;
  }

  return (
    <Box style={{ flex: 1, overflow: 'auto', padding: '16px 20px 20px' }}>
      <Group justify="space-between" px={4} pb={10} style={{ maxWidth: 860 }}>
        <Text fz="xs" c="dimmed">
          {visible.length} {visible.length === 1 ? 'item' : 'items'} to triage
          {query ? ` (of ${items.length})` : ''}
        </Text>
        <Group gap={8}>
          <Button
            size="xs"
            variant="default"
            leftSection={<IconSparkles size={14} />}
            loading={matchAll.isPending || syncing}
            onClick={handleMatchAll}
          >
            Match all
          </Button>
          <TriageRules />
        </Group>
      </Group>
      <Stack gap="sm" style={{ maxWidth: 860 }}>
        {visible.map((item) => (
          <CatchupCard
            key={item.id}
            item={item}
            taskOptions={taskOptions}
            bucketOptions={bucketOptions}
          />
        ))}
      </Stack>
    </Box>
  );
}
