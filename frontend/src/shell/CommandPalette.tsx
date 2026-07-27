import { Spotlight, type SpotlightActionData } from '@mantine/spotlight';
import { IconBulb, IconKeyboard, IconRefresh, IconSearch } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { useTasks } from '../api/hooks';
import { NAV_TARGETS } from '../lib/keyboard';
import { taskPath } from '../lib/tasks';
import type { Task } from '../types';
import { useHq } from './HqContext';

interface CommandPaletteProps {
  onShowHelp: () => void;
}

/**
 * Cmd/Ctrl+K command palette (its open shortcut is registered by Spotlight itself). Fuzzy-searches
 * the jump-to-view targets, every task, and the handful of global actions.
 */
export function CommandPalette({ onShowHelp }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { runSync } = useHq();
  const { data: tasks } = useTasks();
  // Archived tasks are a separate query (the list endpoint returns active or archived, not both).
  const { data: archivedTasks } = useTasks({ archived: true });

  const goTo: SpotlightActionData[] = NAV_TARGETS.map((target) => ({
    id: `go-${target.path}`,
    label: target.label,
    description: `Go to ${target.label}`,
    keywords: ['go', 'open', 'navigate', target.label],
    onClick: () => navigate(target.path),
  }));

  const toTaskAction = (extraKeyword?: string) => (task: Task) => ({
    id: `task-${task.id}`,
    label: task.title,
    description: extraKeyword ? `${task.bucket} · ${extraKeyword}` : task.bucket,
    keywords: ['task', task.bucket, ...task.tags, ...(extraKeyword ? [extraKeyword] : [])],
    onClick: () => navigate(taskPath(task.id)),
  });

  const taskActions: SpotlightActionData[] = (tasks ?? []).map(toTaskAction());
  const archivedActions: SpotlightActionData[] = (archivedTasks ?? []).map(
    toTaskAction('archived'),
  );

  const commands: SpotlightActionData[] = [
    {
      id: 'sync',
      label: 'Sync now',
      description: 'Pull the latest from every source',
      keywords: ['refresh', 'update'],
      leftSection: <IconRefresh size={18} stroke={1.5} />,
      onClick: runSync,
    },
    {
      id: 'braindump',
      label: 'Brain dump',
      description: 'Capture a thought as an item',
      keywords: ['note', 'capture', 'idea'],
      leftSection: <IconBulb size={18} stroke={1.5} />,
      onClick: () => navigate('/braindump'),
    },
    {
      id: 'shortcuts',
      label: 'Keyboard shortcuts',
      description: 'Show every shortcut',
      keywords: ['help', 'keys'],
      leftSection: <IconKeyboard size={18} stroke={1.5} />,
      onClick: onShowHelp,
    },
  ];

  return (
    <Spotlight
      actions={[
        { group: 'Go to', actions: goTo },
        { group: 'Tasks', actions: taskActions },
        { group: 'Archived tasks', actions: archivedActions },
        { group: 'Actions', actions: commands },
      ]}
      highlightQuery
      nothingFound="Nothing found…"
      searchProps={{
        placeholder: 'Type a command or search…',
        leftSection: <IconSearch size={18} stroke={1.5} />,
      }}
    />
  );
}
