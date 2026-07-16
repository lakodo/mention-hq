import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Center,
  Group,
  Loader,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconChevronDown, IconChevronUp, IconTrash } from '@tabler/icons-react';
import { useState } from 'react';
import { CONNECTION_META, UNCATEGORIZED } from '../constants';
import { errorMessage } from '../api/client';
import {
  useAIStatus,
  useBuckets,
  useClearSourceConfig,
  useCreateBucket,
  useDeleteBucket,
  useReassignBuckets,
  useSettings,
  useSources,
  useTestSource,
  useUpdateAIKey,
  useUpdateBucket,
  useUpdateSettings,
  useUpdateSourceConfig,
} from '../api/hooks';
import { formatAgo } from '../lib/time';
import type { Bucket, ConfigField, SourceStatus } from '../types';

function fail(error: unknown) {
  notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });
}

function ok(title: string, message: string) {
  notifications.show({ title, message, color: 'teal' });
}

function AppNameSection() {
  const { data: settings } = useSettings();
  const update = useUpdateSettings();
  const [name, setName] = useState<string | null>(null);
  const value = name ?? settings?.app_name ?? '';

  return (
    <Card withBorder radius="md" p="md">
      <Title order={5} mb="xs">
        App name
      </Title>
      <Text fz="xs" c="dimmed" mb="sm">
        Shown in the header. Secrets are stored in {settings?.secret_backend ?? 'the keychain'}.
      </Text>
      <Group gap="sm">
        <TextInput
          aria-label="App name"
          value={value}
          onChange={(e) => setName(e.currentTarget.value)}
          style={{ flex: 1, maxWidth: 320 }}
        />
        <Button
          loading={update.isPending}
          disabled={!value.trim() || value === settings?.app_name}
          onClick={() =>
            update.mutate(value.trim(), {
              onSuccess: (s) => {
                setName(null);
                ok('Saved', `App name is now ${s.app_name}.`);
              },
              onError: fail,
            })
          }
        >
          Save
        </Button>
      </Group>
    </Card>
  );
}

interface BucketRowProps {
  bucket: Bucket;
  isFirst: boolean;
  isLast: boolean;
}

function BucketRow({ bucket, isFirst, isLast }: BucketRowProps) {
  const update = useUpdateBucket();
  const remove = useDeleteBucket();
  const [keywords, setKeywords] = useState<string | null>(null);

  // Uncategorized has no row of its own in the backend; it cannot be edited or deleted.
  const implicit = bucket.name === UNCATEGORIZED;
  const value = keywords ?? bucket.keywords.join(', ');
  const parsed = value
    .split(',')
    .map((k) => k.trim())
    .filter(Boolean);
  const dirty = value !== bucket.keywords.join(', ');

  const move = (delta: number) =>
    update.mutate(
      { name: bucket.name, patch: { position: bucket.position + delta } },
      { onError: fail },
    );

  return (
    <Card withBorder radius="sm" p="sm" data-testid={`bucket-row-${bucket.name}`}>
      <Group gap="sm" wrap="nowrap">
        <Stack gap={0}>
          <Tooltip label="Move left" withArrow>
            <ActionIcon
              size="sm"
              variant="subtle"
              color="gray"
              aria-label={`Move ${bucket.name} earlier`}
              disabled={implicit || isFirst}
              onClick={() => move(-1)}
            >
              <IconChevronUp size={14} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label="Move right" withArrow>
            <ActionIcon
              size="sm"
              variant="subtle"
              color="gray"
              aria-label={`Move ${bucket.name} later`}
              disabled={implicit || isLast}
              onClick={() => move(1)}
            >
              <IconChevronDown size={14} />
            </ActionIcon>
          </Tooltip>
        </Stack>

        <Box style={{ width: 160, flexShrink: 0 }}>
          <Text fw={600} fz="sm">
            {bucket.name}
          </Text>
          <Text fz="xs" c="dimmed">
            {bucket.count} {bucket.count === 1 ? 'task' : 'tasks'}
          </Text>
        </Box>

        <TextInput
          size="xs"
          aria-label={`Keywords for ${bucket.name}`}
          placeholder={implicit ? 'Whatever matched nothing else' : 'comma, separated, keywords'}
          value={value}
          disabled={implicit}
          onChange={(e) => setKeywords(e.currentTarget.value)}
          style={{ flex: 1 }}
        />

        <Button
          size="xs"
          variant="light"
          disabled={implicit || !dirty}
          loading={update.isPending}
          onClick={() =>
            update.mutate(
              { name: bucket.name, patch: { keywords: parsed } },
              {
                onSuccess: () => {
                  setKeywords(null);
                  ok('Saved', `Keywords updated for ${bucket.name}.`);
                },
                onError: fail,
              },
            )
          }
        >
          Save
        </Button>

        <Tooltip
          label={implicit ? 'Always present' : 'Delete — tasks move to Uncategorized'}
          withArrow
        >
          <ActionIcon
            variant="subtle"
            color="red"
            aria-label={`Delete ${bucket.name}`}
            disabled={implicit}
            loading={remove.isPending}
            onClick={() =>
              remove.mutate(bucket.name, {
                onSuccess: () =>
                  ok('Deleted', `${bucket.name} is gone. Its tasks moved to ${UNCATEGORIZED}.`),
                onError: fail,
              })
            }
          >
            <IconTrash size={16} />
          </ActionIcon>
        </Tooltip>
      </Group>
    </Card>
  );
}

function BucketsSection() {
  const { data: buckets, isLoading } = useBuckets();
  const create = useCreateBucket();
  const reassign = useReassignBuckets();
  const [name, setName] = useState('');
  const [keywords, setKeywords] = useState('');

  const rows = [...(buckets ?? [])].sort((a, b) => a.position - b.position);

  const submit = () =>
    create.mutate(
      {
        name: name.trim(),
        keywords: keywords
          .split(',')
          .map((k) => k.trim())
          .filter(Boolean),
      },
      {
        onSuccess: (bucket) => {
          setName('');
          setKeywords('');
          ok('Bucket created', bucket.name);
        },
        onError: fail,
      },
    );

  return (
    <Card withBorder radius="md" p="md">
      <Group justify="space-between" mb="xs">
        <Title order={5}>Buckets</Title>
        <Button
          size="xs"
          variant="light"
          loading={reassign.isPending}
          onClick={() =>
            reassign.mutate(undefined, {
              onSuccess: () =>
                ok('Re-applied', 'Every task was matched against the keywords again.'),
              onError: fail,
            })
          }
        >
          Re-apply keywords
        </Button>
      </Group>
      <Text fz="xs" c="dimmed" mb="sm">
        Keywords match a task's title and tags. Re-applying skips tasks you moved by hand.
      </Text>

      {isLoading ? (
        <Loader size="sm" />
      ) : (
        <Stack gap={8} mb="md">
          {rows.length === 0 && (
            <Text fz="sm" c="dimmed">
              No buckets yet. Create the first one below.
            </Text>
          )}
          {rows.map((bucket, i) => (
            <BucketRow
              key={bucket.name}
              bucket={bucket}
              isFirst={i === 0}
              isLast={i === rows.length - 1}
            />
          ))}
        </Stack>
      )}

      <Group gap="sm" align="flex-end">
        <TextInput
          size="xs"
          label="New bucket"
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          style={{ width: 180 }}
        />
        <TextInput
          size="xs"
          label="Keywords"
          placeholder="comma, separated"
          value={keywords}
          onChange={(e) => setKeywords(e.currentTarget.value)}
          style={{ flex: 1 }}
        />
        <Button size="xs" disabled={!name.trim()} loading={create.isPending} onClick={submit}>
          Create
        </Button>
      </Group>
    </Card>
  );
}

interface SourceCardProps {
  source: SourceStatus;
}

/**
 * The form is built from `fields`, so a source the backend grows tomorrow gets a
 * working setup form here without a line of code.
 */
function SourceCard({ source }: SourceCardProps) {
  const test = useTestSource();
  const save = useUpdateSourceConfig();
  const clear = useClearSourceConfig();

  // Only the keys the user actually edited are sent — an untouched secret must not be cleared.
  const [edits, setEdits] = useState<Record<string, string>>({});
  const meta = CONNECTION_META[source.status] ?? CONNECTION_META.unconfigured;
  const dirty = Object.keys(edits).length > 0;

  const fieldValue = (field: ConfigField): string =>
    edits[field.key] ?? (field.kind === 'secret' ? '' : (field.value ?? ''));

  const renderField = (field: ConfigField) => {
    const common = {
      size: 'xs' as const,
      label: field.label,
      placeholder: field.placeholder,
      description: field.help || undefined,
      required: field.required,
      value: fieldValue(field),
      onChange: (e: React.ChangeEvent<HTMLInputElement>) => {
        // Read before the updater runs — React has nulled currentTarget by then.
        const value = e.currentTarget.value;
        setEdits((prev) => ({ ...prev, [field.key]: value }));
      },
    };

    if (field.kind === 'secret') {
      return (
        <PasswordInput
          key={field.key}
          {...common}
          placeholder={field.is_set ? (field.value ?? '••••••••') : field.placeholder}
          description={
            field.is_set ? `Stored${field.help ? ` · ${field.help}` : ''}` : common.description
          }
        />
      );
    }
    return <TextInput key={field.key} {...common} />;
  };

  return (
    <Card withBorder radius="md" p="md" data-testid={`source-card-${source.id}`}>
      <Group gap={10} mb={4} wrap="nowrap">
        <Text fw={700} fz="sm" style={{ flex: 1 }}>
          {source.name}
        </Text>
        <Badge size="sm" color={meta.color} variant="light">
          {meta.label}
        </Badge>
      </Group>

      <Text fz="xs" c="dimmed">
        {source.description}
      </Text>
      <Text fz="xs" mt={4}>
        {source.detail}
      </Text>
      {source.error && (
        <Text fz="xs" c="red" mt={4}>
          {source.error}
        </Text>
      )}

      {source.fields.length > 0 && (
        <Stack gap={8} mt="sm">
          {source.fields.map(renderField)}
        </Stack>
      )}

      <Group gap={8} mt="md" justify="space-between">
        <Text fz={10} c="dimmed">
          {source.last_checked_at
            ? `checked ${formatAgo(source.last_checked_at)}`
            : 'never checked'}
        </Text>
        <Group gap={6}>
          {source.fields.length > 0 && (
            <>
              <Button
                size="xs"
                disabled={!dirty}
                loading={save.isPending}
                onClick={() =>
                  save.mutate(
                    { id: source.id, values: edits },
                    {
                      onSuccess: () => {
                        setEdits({});
                        ok('Saved', `${source.name} configuration updated.`);
                      },
                      onError: fail,
                    },
                  )
                }
              >
                Save
              </Button>
              <Button
                size="xs"
                variant="subtle"
                color="red"
                loading={clear.isPending}
                onClick={() =>
                  clear.mutate(source.id, {
                    onSuccess: () => {
                      setEdits({});
                      ok('Cleared', `${source.name} configuration removed.`);
                    },
                    onError: fail,
                  })
                }
              >
                Clear
              </Button>
            </>
          )}
          <Button
            size="xs"
            variant="light"
            loading={test.isPending}
            onClick={() =>
              test.mutate(source.id, {
                onSuccess: (result) =>
                  notifications.show({
                    title: result.name,
                    message: result.error ?? result.detail,
                    color: result.status === 'connected' ? 'teal' : 'orange',
                  }),
                onError: fail,
              })
            }
          >
            Test connection
          </Button>
        </Group>
      </Group>
    </Card>
  );
}

function SourcesSection() {
  const { data: sources, isLoading } = useSources();
  const connected = (sources ?? []).filter((s) => s.status === 'connected').length;

  return (
    <Box>
      <Group align="baseline" gap={10} mb="sm">
        <Title order={5}>Connected sources</Title>
        <Text fz="xs" c="dimmed">
          {connected}/{sources?.length ?? 0} connected
        </Text>
      </Group>

      {isLoading ? (
        <Loader size="sm" />
      ) : (
        <Box
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: 14,
          }}
        >
          {(sources ?? []).map((source) => (
            <SourceCard key={source.id} source={source} />
          ))}
        </Box>
      )}
    </Box>
  );
}

function AISection() {
  const { data: ai } = useAIStatus();
  const update = useUpdateAIKey();
  const [key, setKey] = useState('');

  return (
    <Card withBorder radius="md" p="md">
      <Group gap={10} mb={4}>
        <Title order={5}>AI</Title>
        <Badge size="sm" color={ai?.available ? 'teal' : 'gray'} variant="light">
          {ai?.available ? 'Available' : 'Unavailable'}
        </Badge>
        {ai?.model && (
          <Text fz="xs" c="dimmed">
            {ai.model}
          </Text>
        )}
      </Group>
      <Text fz="xs" c="dimmed" mb="sm">
        {ai?.detail ?? 'Checking…'}
      </Text>

      <Group gap="sm" align="flex-end">
        <PasswordInput
          size="xs"
          label="API key"
          aria-label="API key"
          placeholder={ai?.source === 'keychain' ? '••••••••' : 'sk-ant-…'}
          value={key}
          onChange={(e) => setKey(e.currentTarget.value)}
          style={{ flex: 1, maxWidth: 360 }}
        />
        <Button
          size="xs"
          disabled={!key.trim()}
          loading={update.isPending}
          onClick={() =>
            update.mutate(key.trim(), {
              onSuccess: (status) => {
                setKey('');
                ok('Saved', status.detail);
              },
              onError: fail,
            })
          }
        >
          Save
        </Button>
        <Button
          size="xs"
          variant="subtle"
          color="red"
          disabled={ai?.source !== 'keychain'}
          onClick={() =>
            update.mutate('', {
              onSuccess: (status) => ok('Cleared', status.detail),
              onError: fail,
            })
          }
        >
          Clear
        </Button>
      </Group>
    </Card>
  );
}

export function AdminView() {
  const { isLoading } = useSettings();

  if (isLoading) {
    return (
      <Center style={{ flex: 1 }}>
        <Loader />
      </Center>
    );
  }

  return (
    <Box style={{ flex: 1, overflow: 'auto', padding: '20px 24px' }}>
      <Stack gap="lg" style={{ maxWidth: 1100 }}>
        <AppNameSection />
        <BucketsSection />
        <SourcesSection />
        <AISection />
      </Stack>
    </Box>
  );
}
