import { Spotlight, type SpotlightActionData } from '@mantine/spotlight';
import { IconBulb, IconKeyboard, IconRefresh, IconSearch } from '@tabler/icons-react';
import { useNavigate } from 'react-router-dom';
import { NAV_TARGETS } from '../lib/keyboard';
import { useHq } from './HqContext';

interface CommandPaletteProps {
  onShowHelp: () => void;
}

/**
 * Cmd/Ctrl+K command palette (its open shortcut is registered by Spotlight itself). Fuzzy-searches
 * the same jump-to-view targets the keyboard shortcuts use, plus the handful of global actions.
 */
export function CommandPalette({ onShowHelp }: CommandPaletteProps) {
  const navigate = useNavigate();
  const { runSync } = useHq();

  const goTo: SpotlightActionData[] = NAV_TARGETS.map((target) => ({
    id: `go-${target.path}`,
    label: target.label,
    description: `Go to ${target.label}`,
    keywords: ['go', 'open', 'navigate', target.label],
    onClick: () => navigate(target.path),
  }));

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
