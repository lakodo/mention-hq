import {
  ActionIcon,
  Badge,
  Box,
  Button,
  Card,
  Center,
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
import { IconDots, IconPlus, IconUserPlus, IconX } from '@tabler/icons-react';
import { useMemo, useState } from 'react';
import { errorMessage } from '../api/client';
import {
  useAddIdentity,
  useCreatePerson,
  useDeletePerson,
  useMergePeople,
  usePeople,
  useRemoveIdentity,
  useUpdatePerson,
} from '../api/hooks';
import type { Person } from '../types';

// The handles a person can carry. Freeform on the API; these are the ones worth offering.
const KINDS = ['slack', 'github', 'linear', 'dust', 'email'];

function fail(error: unknown) {
  notifications.show({ title: 'Action failed', message: errorMessage(error), color: 'red' });
}

interface PersonCardProps {
  person: Person;
  others: Person[];
}

function PersonCard({ person, others }: PersonCardProps) {
  const [kind, setKind] = useState<string | null>('slack');
  const [value, setValue] = useState('');
  const [editOpen, setEditOpen] = useState(false);
  const [mergeOpen, setMergeOpen] = useState(false);

  const addIdentity = useAddIdentity();
  const removeIdentity = useRemoveIdentity();
  const deletePerson = useDeletePerson();

  const submitIdentity = () => {
    if (!kind || !value.trim()) return;
    addIdentity.mutate(
      { id: person.id, kind, value: value.trim() },
      { onSuccess: () => setValue(''), onError: fail },
    );
  };

  const confirmDelete = () =>
    modals.openConfirmModal({
      title: `Delete ${person.display_name}?`,
      children: (
        <Text size="sm">This removes the person and all their handles. Items are untouched.</Text>
      ),
      labels: { confirm: 'Delete', cancel: 'Cancel' },
      confirmProps: { color: 'red' },
      onConfirm: () =>
        deletePerson.mutate(person.id, {
          onSuccess: () =>
            notifications.show({
              title: 'Person deleted',
              message: person.display_name,
              color: 'teal',
            }),
          onError: fail,
        }),
    });

  return (
    <Card withBorder radius="md" p="md" data-testid="person-card">
      <Group justify="space-between" wrap="nowrap" mb={6}>
        <Box style={{ minWidth: 0 }}>
          <Text fw={600} truncate>
            {person.display_name}
          </Text>
          {person.email && (
            <Text fz="xs" c="dimmed" truncate>
              {person.email}
            </Text>
          )}
        </Box>
        <Menu position="bottom-end" withArrow>
          <Menu.Target>
            <ActionIcon
              variant="subtle"
              color="gray"
              aria-label={`Actions for ${person.display_name}`}
            >
              <IconDots size={16} />
            </ActionIcon>
          </Menu.Target>
          <Menu.Dropdown>
            <Menu.Item onClick={() => setEditOpen(true)}>Edit</Menu.Item>
            <Menu.Item onClick={() => setMergeOpen(true)} disabled={others.length === 0}>
              Merge into…
            </Menu.Item>
            <Menu.Item color="red" onClick={confirmDelete}>
              Delete
            </Menu.Item>
          </Menu.Dropdown>
        </Menu>
      </Group>

      <EditPerson person={person} opened={editOpen} onClose={() => setEditOpen(false)} />
      <MergePerson
        person={person}
        others={others}
        opened={mergeOpen}
        onClose={() => setMergeOpen(false)}
      />

      <Group gap={6} mb="sm">
        {person.identities.length === 0 && (
          <Text fz="xs" c="dimmed">
            No handles yet.
          </Text>
        )}
        {person.identities.map((identity) => (
          <Badge
            key={identity.id}
            variant="light"
            radius="sm"
            rightSection={
              <ActionIcon
                size={14}
                variant="transparent"
                color="gray"
                aria-label={`Remove ${identity.kind} ${identity.value}`}
                onClick={() =>
                  removeIdentity.mutate(
                    { id: person.id, identityId: identity.id },
                    { onError: fail },
                  )
                }
              >
                <IconX size={11} />
              </ActionIcon>
            }
          >
            {identity.kind}:{identity.value}
          </Badge>
        ))}
      </Group>

      <Group gap={8} wrap="nowrap">
        <Select
          size="xs"
          data={KINDS}
          value={kind}
          onChange={setKind}
          aria-label="Handle kind"
          w={110}
          comboboxProps={{ withinPortal: true }}
        />
        <TextInput
          size="xs"
          placeholder="id, login or address"
          aria-label={`New handle for ${person.display_name}`}
          value={value}
          onChange={(e) => setValue(e.currentTarget.value)}
          onKeyDown={(e) => e.key === 'Enter' && submitIdentity()}
          style={{ flex: 1 }}
        />
        <Button
          size="xs"
          variant="light"
          leftSection={<IconPlus size={13} />}
          disabled={!value.trim()}
          onClick={submitIdentity}
        >
          Add
        </Button>
      </Group>
    </Card>
  );
}

interface ModalProps {
  opened: boolean;
  onClose: () => void;
}

function EditPerson({ person, opened, onClose }: { person: Person } & ModalProps) {
  const [name, setName] = useState(person.display_name);
  const [email, setEmail] = useState(person.email ?? '');
  const update = useUpdatePerson();

  const save = () =>
    update.mutate(
      { id: person.id, patch: { display_name: name.trim(), email: email.trim() || null } },
      { onSuccess: onClose, onError: fail },
    );

  return (
    <Modal opened={opened} onClose={onClose} title="Edit person">
      <Stack gap="sm">
        <TextInput
          label="Name"
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
          data-autofocus
        />
        <TextInput label="Email" value={email} onChange={(e) => setEmail(e.currentTarget.value)} />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={save} loading={update.isPending} disabled={!name.trim()}>
            Save
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function MergePerson({
  person,
  others,
  opened,
  onClose,
}: { person: Person; others: Person[] } & ModalProps) {
  const [target, setTarget] = useState<string | null>(null);
  const merge = useMergePeople();

  const run = () => {
    if (!target) return;
    merge.mutate(
      { sourceId: person.id, into: target },
      {
        onSuccess: (kept) => {
          onClose();
          notifications.show({
            title: 'Merged',
            message: `${person.display_name} folded into ${kept.display_name}.`,
            color: 'teal',
          });
        },
        onError: fail,
      },
    );
  };

  return (
    <Modal opened={opened} onClose={onClose} title={`Merge ${person.display_name} into…`}>
      <Stack gap="sm">
        <Text fz="sm" c="dimmed">
          {person.display_name}&rsquo;s handles move to the person you pick, and{' '}
          {person.display_name} is removed.
        </Text>
        <Select
          data={others.map((p) => ({ value: p.id, label: p.display_name }))}
          value={target}
          onChange={setTarget}
          placeholder="Keep this person"
          aria-label="Merge target"
          searchable
        />
        <Group justify="flex-end">
          <Button variant="subtle" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={run} loading={merge.isPending} disabled={!target}>
            Merge
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function AddPerson() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const create = useCreatePerson();

  const save = () =>
    create.mutate(
      { display_name: name.trim(), email: email.trim() || null },
      {
        onSuccess: () => {
          setOpen(false);
          setName('');
          setEmail('');
        },
        onError: fail,
      },
    );

  return (
    <>
      <Button leftSection={<IconUserPlus size={16} />} onClick={() => setOpen(true)}>
        Add person
      </Button>
      <Modal opened={open} onClose={() => setOpen(false)} title="Add a person">
        <Stack gap="sm">
          <TextInput
            label="Name"
            value={name}
            onChange={(e) => setName(e.currentTarget.value)}
            data-autofocus
          />
          <TextInput
            label="Email"
            value={email}
            onChange={(e) => setEmail(e.currentTarget.value)}
          />
          <Group justify="flex-end">
            <Button variant="subtle" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button onClick={save} loading={create.isPending} disabled={!name.trim()}>
              Add
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

export function PeopleView() {
  const { data: people, isLoading } = usePeople();
  const sorted = useMemo(
    () => [...(people ?? [])].sort((a, b) => a.display_name.localeCompare(b.display_name)),
    [people],
  );

  if (isLoading) {
    return (
      <Center style={{ flex: 1 }}>
        <Loader />
      </Center>
    );
  }

  return (
    <Box style={{ flex: 1, overflow: 'auto', padding: '20px' }}>
      <Group justify="space-between" mb="md" style={{ maxWidth: 820 }}>
        <Text fz="sm" c="dimmed">
          {sorted.length} {sorted.length === 1 ? 'person' : 'people'} — one identity per source,
          merged into one.
        </Text>
        <AddPerson />
      </Group>

      {sorted.length === 0 ? (
        <Text c="dimmed" fz="sm">
          No one yet. Sync a source to discover people, or add one by hand.
        </Text>
      ) : (
        <Stack gap="sm" style={{ maxWidth: 820 }}>
          {sorted.map((person) => (
            <PersonCard
              key={person.id}
              person={person}
              others={sorted.filter((p) => p.id !== person.id)}
            />
          ))}
        </Stack>
      )}
    </Box>
  );
}
