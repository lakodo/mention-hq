import {
  ActionIcon,
  Anchor,
  Badge,
  Box,
  Button,
  Center,
  Group,
  Loader,
  MultiSelect,
  Select,
  Stack,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { IconSortAscending, IconSortDescending } from '@tabler/icons-react';
import { useMemo, useState } from 'react';
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

type Attachment = 'any' | 'filed' | 'untriaged';

export function TimelineView() {
  const navigate = useNavigate();
  const { query } = useHq();
  const { data: items, isLoading } = useItems();

  const [kinds, setKinds] = useState<string[]>([]);
  const [text, setText] = useState('');
  const [attachment, setAttachment] = useState<Attachment>('any');
  const [oldestFirst, setOldestFirst] = useState(false);

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
        rows.map((item) => {
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
        })
      )}
    </Box>
  );
}
