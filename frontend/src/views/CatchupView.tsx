import {
  Anchor,
  Badge,
  Box,
  Button,
  Card,
  Center,
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
import { IconExternalLink } from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { SourceDot } from '../components/SourceDot';
import { LINK_STATE_META, sourceMeta } from '../constants';
import { errorMessage } from '../api/client';
import {
  useBuckets,
  useCatchup,
  useConfirmLinks,
  useCreateTaskFromItem,
  useRejectLink,
  useTasks,
  useTriageItem,
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

  const busy = confirm.isPending || reject.isPending || triage.isPending || createTask.isPending;
  const meta = sourceMeta(item.source);

  const fail = (error: unknown) =>
    notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });

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
          // Inline: this list sits in a full-width card, so it never clips — and it keeps
          // each card's options scoped to that card. Modal dropdowns portal (they clip).
          comboboxProps={{ withinPortal: false }}
        />
        <Button size="sm" disabled={busy || selected.length === 0} onClick={() => attach(selected)}>
          Attach
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

export function CatchupView() {
  const { query } = useHq();
  const { data: items, isLoading } = useCatchup();
  const { data: tasks } = useTasks();
  const { data: buckets } = useBuckets();

  const taskOptions = useMemo(
    () =>
      (tasks ?? []).map((task) => ({ value: task.id, label: `${task.title} · ${task.bucket}` })),
    [tasks],
  );
  const bucketOptions = useMemo(() => (buckets ?? []).map((b) => b.name), [buckets]);
  const visible = useMemo(() => filterItems(items ?? [], query), [items, query]);

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
      <Text fz="xs" c="dimmed" px={4} pb={10}>
        {visible.length} {visible.length === 1 ? 'item' : 'items'} to triage
        {query ? ` (of ${items.length})` : ''}
      </Text>
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
