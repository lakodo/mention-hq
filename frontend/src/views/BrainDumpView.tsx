import {
  Button,
  Center,
  Group,
  MultiSelect,
  Stack,
  Text,
  Textarea,
  TextInput,
} from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '../api/client';
import { useCreateNote, useTasks } from '../api/hooks';

export function BrainDumpView() {
  const navigate = useNavigate();
  const { data: tasks } = useTasks();
  const createNote = useCreateNote();
  const [text, setText] = useState('');
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [taskIds, setTaskIds] = useState<string[]>([]);

  const taskOptions = useMemo(
    () =>
      (tasks ?? []).map((task) => ({ value: task.id, label: `${task.title} · ${task.bucket}` })),
    [tasks],
  );

  // A link needs no body; a plain note does — so allow submit when either is filled.
  const canSubmit = Boolean(text.trim() || url.trim());

  const submit = () => {
    if (!canSubmit) return;
    createNote.mutate(
      {
        text: text.trim(),
        taskIds,
        url: url.trim() || undefined,
        title: title.trim() || undefined,
      },
      {
        onSuccess: () => {
          notifications.show({
            title: 'Captured',
            message: taskIds.length ? 'Filed onto your task.' : 'Added to Catch-up.',
            color: 'teal',
          });
          setText('');
          setUrl('');
          setTitle('');
          setTaskIds([]);
          navigate(taskIds.length ? '/task' : '/catchup');
        },
        onError: (error) =>
          notifications.show({ title: 'Failed', message: errorMessage(error), color: 'red' }),
      },
    );
  };

  return (
    <Center style={{ flex: 1, padding: '24px' }}>
      <Stack w="100%" maw={640} gap="md">
        <Stack gap={2}>
          <Text fw={700} fz="xl">
            Brain dump
          </Text>
          <Text c="dimmed" fz="sm">
            Type anything — it becomes an item and flows into Catch-up, or straight onto a task if
            you pick one. Add a link to save a clickable URL; the text becomes its description.
          </Text>
        </Stack>

        <TextInput
          placeholder="Link (optional) — https://…"
          value={url}
          onChange={(e) => setUrl(e.currentTarget.value)}
          aria-label="Link URL"
        />
        {url.trim() && (
          <TextInput
            placeholder="Title (optional)"
            value={title}
            onChange={(e) => setTitle(e.currentTarget.value)}
            aria-label="Link title"
          />
        )}

        <Textarea
          autosize
          minRows={6}
          maxRows={20}
          placeholder={
            url.trim() ? 'Why this matters — helps decide the next action' : "What's on your mind?"
          }
          value={text}
          onChange={(e) => setText(e.currentTarget.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') submit();
          }}
          data-autofocus
          aria-label="Brain dump text"
        />

        <Group gap={8} align="flex-end" wrap="nowrap">
          <MultiSelect
            data={taskOptions}
            value={taskIds}
            onChange={setTaskIds}
            placeholder="Attach to tasks (optional)…"
            aria-label="Attach to tasks"
            searchable
            clearable
            style={{ flex: 1, minWidth: 0 }}
            comboboxProps={{ withinPortal: true }}
          />
          <Button onClick={submit} loading={createNote.isPending} disabled={!canSubmit}>
            Capture
          </Button>
        </Group>
        <Text c="dimmed" fz="xs" ta="right">
          ⌘/Ctrl + Enter to capture
        </Text>
      </Stack>
    </Center>
  );
}
