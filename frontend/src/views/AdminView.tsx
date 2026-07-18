import {
  ActionIcon,
  Anchor,
  Badge,
  Box,
  Code,
  CopyButton,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Menu,
  Modal,
  PasswordInput,
  ScrollArea,
  Select,
  Stack,
  Text,
  TextInput,
  Title,
  Tooltip,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import {
  IconChevronDown,
  IconChevronUp,
  IconPencil,
  IconPlus,
  IconSparkles,
  IconTrash,
} from '@tabler/icons-react';
import { useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { CONNECTION_META, UNCATEGORIZED } from '../constants';
import { errorMessage, startNotionAuthorize } from '../api/client';
import {
  useAIStatus,
  useAddSource,
  useBackupDatabase,
  useBuckets,
  useCreateBucket,
  useDeleteBucket,
  useDetectSource,
  useEnrichTasks,
  useNotionOauth,
  queryKeys,
  useReassignBuckets,
  useRemoveSource,
  useRenameSource,
  useSettings,
  useSourceKinds,
  useSources,
  useTestSource,
  useUpdateAIKey,
  useUpdateBucket,
  useUpdateSettings,
  useUpdateSourceConfig,
} from '../api/hooks';
import { formatAgo } from '../lib/time';
import type { Bucket, ConfigField, Detection, SourceKind, SourceStatus } from '../types';

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
            update.mutate(
              { app_name: value.trim() },
              {
                onSuccess: (s) => {
                  setName(null);
                  ok('Saved', `App name is now ${s.app_name}.`);
                },
                onError: fail,
              },
            )
          }
        >
          Save
        </Button>
      </Group>
    </Card>
  );
}

function DatabaseSection() {
  const backup = useBackupDatabase();

  return (
    <Card withBorder radius="md" p="md">
      <Title order={5} mb="xs">
        Database
      </Title>
      <Text fz="xs" c="dimmed" mb="sm">
        Save a timestamped copy into <code>backups/</code> next to the live file. Migrations do this
        automatically; use this before anything else risky.
      </Text>
      <Button
        variant="light"
        loading={backup.isPending}
        onClick={() =>
          backup.mutate(undefined, {
            onSuccess: (b) => ok('Backed up', `Saved to ${b.filename}.`),
            onError: fail,
          })
        }
      >
        Back up now
      </Button>
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
              remove.mutate(
                { name: bucket.name },
                {
                  onSuccess: () =>
                    ok('Deleted', `${bucket.name} is gone. Its tasks moved to ${UNCATEGORIZED}.`),
                  onError: fail,
                },
              )
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

interface ManifestProps {
  manifest: string;
  hint: string;
}

/** A config blob the user pastes into the other service — must be trivially copyable. */
function Manifest({ manifest, hint }: ManifestProps) {
  if (!manifest) return null;
  return (
    <Box mt={8}>
      <Group justify="space-between" mb={4} wrap="nowrap">
        <Text fz="xs" c="dimmed">
          {hint}
        </Text>
        <CopyButton value={manifest} timeout={1500}>
          {({ copied, copy }) => (
            <Button size="compact-xs" variant={copied ? 'light' : 'default'} onClick={copy}>
              {copied ? 'Copied' : 'Copy'}
            </Button>
          )}
        </CopyButton>
      </Group>
      <ScrollArea.Autosize mah={220} type="auto">
        <Code block fz="xs">
          {manifest}
        </Code>
      </ScrollArea.Autosize>
    </Box>
  );
}

interface SetupHelpProps {
  setup: string;
  url: string;
  label?: string;
}

/** The answer to "where do I even get this token" — on the card, not in a doc. */
function SetupHelp({ setup, url, label = 'How to get this' }: SetupHelpProps) {
  if (!setup && !url) return null;
  return (
    <Text fz="xs" c="dimmed" mt={6}>
      {setup}
      {url && (
        <>
          {setup && ' '}
          <Anchor href={url} target="_blank" rel="noreferrer" fz="xs">
            {label}
          </Anchor>
        </>
      )}
    </Text>
  );
}

function AddSourceControl() {
  const { data: kinds } = useSourceKinds();
  const add = useAddSource();
  const [picked, setPicked] = useState<SourceKind | null>(null);
  const [name, setName] = useState('');

  const pick = (kind: SourceKind) => {
    setPicked(kind);
    setName(kind.name);
  };

  const submit = () => {
    if (!picked) return;
    add.mutate(
      { kind: picked.kind, name: name.trim() },
      {
        onSuccess: (source) => {
          setPicked(null);
          ok('Source added', `${source.name} is ready to set up.`);
        },
        onError: fail,
      },
    );
  };

  return (
    <>
      <Menu position="bottom-end" withArrow>
        <Menu.Target>
          <Button size="xs" leftSection={<IconPlus size={14} />}>
            Add a source
          </Button>
        </Menu.Target>
        <Menu.Dropdown style={{ maxWidth: 320 }}>
          {(kinds ?? []).map((kind) => (
            <Menu.Item key={kind.kind} onClick={() => pick(kind)}>
              <Text fz="sm" fw={600}>
                {kind.name}
              </Text>
              <Text fz="xs" c="dimmed">
                {kind.description}
              </Text>
            </Menu.Item>
          ))}
        </Menu.Dropdown>
      </Menu>

      <Modal
        opened={picked !== null}
        onClose={() => setPicked(null)}
        title={picked ? `Add ${picked.name}` : ''}
        centered
      >
        {picked && (
          <Stack gap="sm">
            <Text fz="xs" c="dimmed">
              {picked.description}
            </Text>
            <TextInput
              size="xs"
              label="Name"
              description="How you'll tell this one apart from another of the same kind."
              placeholder={picked.name}
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
            />
            <SetupHelp setup={picked.setup} url={picked.setup_url} />
            <Manifest manifest={picked.manifest} hint={picked.manifest_hint} />
            <Group justify="flex-end" gap={6}>
              <Button size="xs" variant="default" onClick={() => setPicked(null)}>
                Cancel
              </Button>
              <Button size="xs" disabled={!name.trim()} loading={add.isPending} onClick={submit}>
                Add
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </>
  );
}

interface SourceCardProps {
  source: SourceStatus;
}

/**
 * The form is built from `fields`, so a source the backend grows tomorrow gets a
 * working setup form here without a line of code.
 */
/**
 * Notion can't use a pasted token when an admin blocks static tokens, so it authenticates
 * over OAuth. The redirect URI is detected from the browser's own origin — every user is on
 * a different host (localhost, a Caddy domain) — and shown here to register in Notion.
 */
function NotionConnect({ source }: { source: SourceStatus }) {
  const info = useNotionOauth(source.id, source.kind === 'notion');
  const qc = useQueryClient();
  const [connecting, setConnecting] = useState(false);

  if (!info.data) return null;
  const { redirect_uri, oauth_ready, connected } = info.data;

  const connect = async () => {
    setConnecting(true);
    try {
      const url = await startNotionAuthorize(source.id);
      const popup = window.open(url, 'notion-oauth', 'width=720,height=820');
      // Re-check status once the consent popup is done, so the card flips to Connected.
      const timer = window.setInterval(() => {
        if (popup && !popup.closed) return;
        window.clearInterval(timer);
        setConnecting(false);
        void qc.invalidateQueries({ queryKey: queryKeys.notionOauth(source.id) });
        void qc.invalidateQueries({ queryKey: queryKeys.sources() });
      }, 800);
    } catch (error) {
      setConnecting(false);
      fail(error);
    }
  };

  return (
    <Stack gap={6} mt="sm">
      <Box>
        <Text fz="xs" fw={600}>
          Redirect URI
        </Text>
        <Text fz="xs" c="dimmed">
          Register this exact URL in your Notion connection.
        </Text>
        <Group gap={6} mt={4} wrap="nowrap">
          <Code style={{ flex: 1, overflowX: 'auto', whiteSpace: 'nowrap' }}>{redirect_uri}</Code>
          <CopyButton value={redirect_uri} timeout={1500}>
            {({ copied, copy }) => (
              <Button size="xs" variant="light" onClick={copy}>
                {copied ? 'Copied' : 'Copy'}
              </Button>
            )}
          </CopyButton>
        </Group>
      </Box>
      <Group gap={8}>
        <Button size="xs" onClick={connect} loading={connecting} disabled={!oauth_ready}>
          {connected ? 'Reconnect to Notion' : 'Connect to Notion'}
        </Button>
        {!oauth_ready && (
          <Text fz="xs" c="dimmed">
            Save the client ID and secret first.
          </Text>
        )}
      </Group>
    </Stack>
  );
}

function SourceCard({ source }: SourceCardProps) {
  const test = useTestSource();
  const save = useUpdateSourceConfig();
  const detect = useDetectSource();
  const rename = useRenameSource();
  const remove = useRemoveSource();

  // Only the keys the user actually edited are sent — an untouched secret must not be cleared.
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [detection, setDetection] = useState<Detection | null>(null);
  const [draftName, setDraftName] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  const meta = CONNECTION_META[source.status] ?? CONNECTION_META.unconfigured;
  const dirty = Object.keys(edits).length > 0;
  const choices = detection?.available ? detection.choices : {};

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

    // `help` is already the input's description; the link is what it can't carry.
    const help = field.help_url ? (
      <SetupHelp setup="" url={field.help_url} label="Create a token" />
    ) : undefined;

    // A tool that knows the options turns a "type it exactly right" field into a pick.
    const options = choices[field.key];
    if (options) {
      return (
        <Select
          key={field.key}
          size="xs"
          label={field.label}
          description={field.help || undefined}
          required={field.required}
          placeholder="Pick one"
          data={options}
          value={fieldValue(field) || null}
          onChange={(value) => setEdits((prev) => ({ ...prev, [field.key]: value ?? '' }))}
        />
      );
    }

    if (field.kind === 'secret') {
      return (
        <Box key={field.key}>
          <PasswordInput
            {...common}
            placeholder={field.is_set ? (field.value ?? '••••••••') : field.placeholder}
            description={
              field.is_set ? `Stored${field.help ? ` · ${field.help}` : ''}` : common.description
            }
          />
          {help}
        </Box>
      );
    }
    return (
      <Box key={field.key}>
        <TextInput {...common} />
        {help}
      </Box>
    );
  };

  const submitName = () => {
    const next = (draftName ?? '').trim();
    if (!next || next === source.name) {
      setDraftName(null);
      return;
    }
    rename.mutate(
      { id: source.id, patch: { name: next } },
      {
        onSuccess: (updated) => {
          setDraftName(null);
          ok('Renamed', `Now called ${updated.name}.`);
        },
        onError: fail,
      },
    );
  };

  return (
    <Card withBorder radius="md" p="md" data-testid={`source-card-${source.id}`}>
      <Group gap={10} mb={4} wrap="nowrap">
        {draftName === null ? (
          <>
            <Text fw={700} fz="sm" style={{ flex: 1 }}>
              {source.name}
            </Text>
            <Tooltip label="Rename" withArrow>
              <ActionIcon
                size="sm"
                variant="subtle"
                color="gray"
                aria-label={`Rename ${source.name}`}
                onClick={() => setDraftName(source.name)}
              >
                <IconPencil size={14} />
              </ActionIcon>
            </Tooltip>
          </>
        ) : (
          <>
            <TextInput
              size="xs"
              aria-label={`Name for ${source.name}`}
              value={draftName}
              onChange={(e) => setDraftName(e.currentTarget.value)}
              style={{ flex: 1 }}
            />
            <Button size="xs" loading={rename.isPending} onClick={submitName}>
              Rename
            </Button>
          </>
        )}
        <Badge size="sm" color={meta.color} variant="light">
          {meta.label}
        </Badge>
      </Group>

      <Group gap={6} mb={2}>
        <Badge size="xs" variant="default">
          {source.kind}
        </Badge>
        <Text fz="xs" c="dimmed">
          {source.description}
        </Text>
      </Group>

      <Text fz="xs" mt={4}>
        {source.detail}
      </Text>
      {source.error && (
        <Text fz="xs" c="red" mt={4}>
          {source.error}
        </Text>
      )}

      <SetupHelp setup={source.setup} url={source.setup_url} />
      <Manifest manifest={source.manifest} hint={source.manifest_hint} />

      {detection && (
        <Text fz="xs" mt={6} c={detection.available ? 'teal' : 'orange'}>
          {detection.detail}
        </Text>
      )}

      {source.fields.length > 0 && (
        <Box
          mt="sm"
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
            gap: 12,
            alignItems: 'start',
          }}
        >
          {source.fields.map(renderField)}
        </Box>
      )}

      {source.kind === 'notion' && <NotionConnect source={source} />}

      <Group gap={8} mt="md" justify="space-between">
        <Text fz={10} c="dimmed">
          {source.last_checked_at
            ? `checked ${formatAgo(source.last_checked_at)}`
            : 'never checked'}
        </Text>
        <Group gap={6}>
          {source.fields.length > 0 && (
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
          )}
          {source.detectable && (
            <Button
              size="xs"
              variant="light"
              loading={detect.isPending}
              onClick={() =>
                detect.mutate(source.id, {
                  onSuccess: (result) => {
                    setDetection(result);
                    // What the tool filled in server-side wins over a half-typed guess.
                    if (result.available) setEdits({});
                  },
                  onError: fail,
                })
              }
            >
              Detect
            </Button>
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
          <Tooltip label="Remove" withArrow>
            <ActionIcon
              variant="subtle"
              color="red"
              aria-label={`Remove ${source.name}`}
              onClick={() => setConfirming(true)}
            >
              <IconTrash size={16} />
            </ActionIcon>
          </Tooltip>
          <Modal
            opened={confirming}
            onClose={() => setConfirming(false)}
            title={`Remove ${source.name}?`}
            centered
          >
            <Stack gap="sm">
              <Text fz="sm">
                Its credentials are deleted with it. Items it already brought in stay on their
                tasks.
              </Text>
              <Group gap={6} justify="flex-end">
                <Button size="xs" variant="default" onClick={() => setConfirming(false)}>
                  Cancel
                </Button>
                <Button
                  size="xs"
                  color="red"
                  loading={remove.isPending}
                  onClick={() =>
                    remove.mutate(source.id, {
                      onSuccess: () => ok('Removed', `${source.name} is gone.`),
                      onError: fail,
                    })
                  }
                >
                  Remove
                </Button>
              </Group>
            </Stack>
          </Modal>
        </Group>
      </Group>
    </Card>
  );
}

function SourcesSection() {
  const { data: sources, isLoading } = useSources();
  const rows = [...(sources ?? [])].sort((a, b) => a.position - b.position);
  const connected = rows.filter((s) => s.status === 'connected').length;

  return (
    <Box>
      <Group justify="space-between" mb="sm">
        <Group align="baseline" gap={10}>
          <Title order={5}>Connected sources</Title>
          {rows.length > 0 && (
            <Text fz="xs" c="dimmed">
              {connected}/{rows.length} connected
            </Text>
          )}
        </Group>
        <AddSourceControl />
      </Group>

      {isLoading ? (
        <Loader size="sm" />
      ) : rows.length === 0 ? (
        <Card withBorder radius="md" p="lg">
          <Text fz="sm" fw={600}>
            No sources yet
          </Text>
          <Text fz="xs" c="dimmed" mt={4}>
            Add a source to start pulling in items. You can add several of the same kind — two
            GitHub accounts, three todo folders.
          </Text>
        </Card>
      ) : (
        <Stack gap={12}>
          {rows.map((source) => (
            <SourceCard key={source.id} source={source} />
          ))}
        </Stack>
      )}
    </Box>
  );
}

function AISection() {
  const { data: ai } = useAIStatus();
  const update = useUpdateAIKey();
  const enrich = useEnrichTasks();
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

      <Text fz="xs" c="dimmed" mt="md" mb={6}>
        Precompute the next action for every task that doesn't have one yet — the tasks that predate
        this feature. New attachments recompute theirs automatically.
      </Text>
      <Button
        size="xs"
        variant="light"
        color="indigo"
        leftSection={<IconSparkles size={14} />}
        loading={enrich.isPending}
        disabled={!ai?.available}
        onClick={() =>
          enrich.mutate(undefined, {
            onSuccess: (r) =>
              ok(
                'Working on it',
                `Computing next actions for ${r.scheduled} tasks in the background.`,
              ),
            onError: fail,
          })
        }
      >
        Compute next actions
      </Button>
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
        <DatabaseSection />
        <BucketsSection />
        <SourcesSection />
        <AISection />
      </Stack>
    </Box>
  );
}
