import { ActionIcon, Button, Group, Modal, Textarea, Tooltip } from '@mantine/core';
import { useDisclosure } from '@mantine/hooks';
import { notifications } from '@mantine/notifications';
import { IconPencil } from '@tabler/icons-react';
import { useState } from 'react';
import { errorMessage } from '../api/client';
import { useUpdateNote } from '../api/hooks';
import type { Item } from '../types';

/** Edit a brain-dump note in place. Only meaningful for `source === 'note'` items. */
export function NoteEditButton({ item }: { item: Item }) {
  const [opened, { open, close }] = useDisclosure(false);
  const [text, setText] = useState(item.label);
  const update = useUpdateNote();

  const save = () =>
    update.mutate(
      { itemId: item.id, text: text.trim() },
      {
        onSuccess: () => {
          notifications.show({ title: 'Note saved', message: text.trim(), color: 'teal' });
          close();
        },
        onError: (error) =>
          notifications.show({ title: 'Failed', message: errorMessage(error), color: 'red' }),
      },
    );

  return (
    <>
      <Tooltip label="Edit note" withArrow>
        <ActionIcon
          size="sm"
          variant="subtle"
          color="gray"
          aria-label="Edit note"
          onClick={() => {
            setText(item.label);
            open();
          }}
        >
          <IconPencil size={14} />
        </ActionIcon>
      </Tooltip>
      <Modal opened={opened} onClose={close} title="Edit note" withinPortal>
        <Textarea
          autosize
          minRows={4}
          value={text}
          onChange={(e) => setText(e.currentTarget.value)}
          data-autofocus
          aria-label="Note text"
        />
        <Group justify="flex-end" mt="sm">
          <Button variant="subtle" onClick={close}>
            Cancel
          </Button>
          <Button onClick={save} loading={update.isPending} disabled={!text.trim()}>
            Save
          </Button>
        </Group>
      </Modal>
    </>
  );
}
