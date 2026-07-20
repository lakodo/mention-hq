import {
  Alert,
  Badge,
  Button,
  Group,
  Loader,
  Modal,
  ScrollArea,
  Text,
  UnstyledButton,
} from '@mantine/core';
import { IconArrowUp, IconBrandGit, IconFolder } from '@tabler/icons-react';
import { useEffect, useState } from 'react';
import { browsePath, errorMessage } from '../api/client';
import type { BrowseResult } from '../types';

interface RepoBrowserProps {
  opened: boolean;
  onClose: () => void;
  onPick: (path: string) => void;
}

/**
 * A filesystem picker for a repo path, so it can be clicked rather than typed exactly right.
 * Descend by clicking a folder; add either a listed folder or the one you're currently in.
 * Git repositories are marked, but any folder can be added — a worktree hides its `.git`.
 */
export function RepoBrowser({ opened, onClose, onPick }: RepoBrowserProps) {
  const [data, setData] = useState<BrowseResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const go = (path?: string) => {
    setLoading(true);
    setError(null);
    browsePath(path)
      .then(setData)
      .catch((e) => setError(errorMessage(e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (opened) go(data?.path);
    // Only re-open resets the listing; navigating within is handled by go().
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  const add = (path: string) => {
    onPick(path);
    onClose();
  };

  return (
    <Modal opened={opened} onClose={onClose} title="Choose a repository" size="lg" withinPortal>
      <Group gap={8} wrap="nowrap" mb="sm">
        <Button
          size="xs"
          variant="default"
          leftSection={<IconArrowUp size={14} />}
          disabled={!data?.parent || loading}
          onClick={() => go(data?.parent ?? undefined)}
        >
          Up
        </Button>
        <Text
          fz="xs"
          c="dimmed"
          style={{ fontFamily: 'var(--mantine-font-family-monospace)' }}
          truncate
        >
          {data?.path ?? '…'}
        </Text>
      </Group>

      {error ? (
        <Alert color="red" mb="sm">
          {error}
        </Alert>
      ) : null}

      <ScrollArea.Autosize mah={360} type="auto">
        {loading && !data ? (
          <Group justify="center" py="lg">
            <Loader size="sm" />
          </Group>
        ) : data && data.entries.length === 0 ? (
          <Text fz="sm" c="dimmed" ta="center" py="lg">
            No sub-folders here.
          </Text>
        ) : (
          data?.entries.map((entry) => (
            <Group key={entry.path} gap={8} wrap="nowrap" py={4}>
              <UnstyledButton
                onClick={() => go(entry.path)}
                style={{ flex: 1, minWidth: 0, display: 'flex', alignItems: 'center', gap: 8 }}
              >
                {entry.is_repo ? (
                  <IconBrandGit size={16} color="var(--mantine-color-grape-6)" />
                ) : (
                  <IconFolder size={16} color="var(--mantine-color-gray-6)" />
                )}
                <Text fz="sm" truncate>
                  {entry.name}
                </Text>
                {entry.is_repo ? (
                  <Badge size="xs" color="grape" variant="light">
                    git
                  </Badge>
                ) : null}
              </UnstyledButton>
              <Button size="compact-xs" variant="light" onClick={() => add(entry.path)}>
                Add
              </Button>
            </Group>
          ))
        )}
      </ScrollArea.Autosize>

      <Group justify="flex-end" gap={8} mt="md">
        <Button size="xs" variant="subtle" onClick={onClose}>
          Cancel
        </Button>
        <Button size="xs" disabled={!data} onClick={() => data && add(data.path)}>
          Add this folder
        </Button>
      </Group>
    </Modal>
  );
}
