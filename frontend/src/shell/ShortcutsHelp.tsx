import { Group, Kbd, Modal, Stack, Table, Text } from '@mantine/core';
import { NAV_TARGETS } from '../lib/keyboard';

interface ShortcutsHelpProps {
  opened: boolean;
  onClose: () => void;
}

/** A row of keys, joined by "then" for sequences and shown side by side for alternatives. */
function Keys({ groups }: { groups: string[][] }) {
  return (
    <Group gap={6} wrap="nowrap">
      {groups.map((keys, gi) => (
        <Group gap={4} wrap="nowrap" key={gi}>
          {gi > 0 && (
            <Text fz="xs" c="dimmed">
              or
            </Text>
          )}
          {keys.map((key, ki) => (
            <Group gap={4} wrap="nowrap" key={ki}>
              {ki > 0 && (
                <Text fz="xs" c="dimmed">
                  then
                </Text>
              )}
              <Kbd>{key}</Kbd>
            </Group>
          ))}
        </Group>
      ))}
    </Group>
  );
}

function Section({ title, rows }: { title: string; rows: { keys: string[][]; label: string }[] }) {
  return (
    <Stack gap={6}>
      <Text fz="xs" fw={700} tt="uppercase" c="dimmed" style={{ letterSpacing: '0.04em' }}>
        {title}
      </Text>
      <Table verticalSpacing={4} horizontalSpacing={0} withRowBorders={false}>
        <Table.Tbody>
          {rows.map((row) => (
            <Table.Tr key={row.label}>
              <Table.Td style={{ width: 200 }}>
                <Keys groups={row.keys} />
              </Table.Td>
              <Table.Td>
                <Text fz="sm">{row.label}</Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Stack>
  );
}

// "⌘" reads on macOS; other platforms send Ctrl. The palette itself accepts either.
const MOD = typeof navigator !== 'undefined' && /Mac/i.test(navigator.platform) ? '⌘' : 'Ctrl';

export function ShortcutsHelp({ opened, onClose }: ShortcutsHelpProps) {
  const navigate = NAV_TARGETS.map((t) => ({
    keys: [['g', t.letter], [String(t.number)]],
    label: `Go to ${t.label}`,
  }));

  return (
    <Modal opened={opened} onClose={onClose} title="Keyboard shortcuts" size="lg">
      <Stack gap="lg">
        <Section
          title="Global"
          rows={[
            { keys: [[MOD, 'K']], label: 'Open the command palette' },
            { keys: [['/']], label: 'Focus the search box' },
            { keys: [['?']], label: 'Show this help' },
            { keys: [['Esc']], label: 'Close a dialog · clear search' },
          ]}
        />
        <Section title="Go to a view" rows={navigate} />
        <Section
          title="Within a list or menu"
          rows={[
            { keys: [['←'], ['→']], label: 'Move between tabs or board columns' },
            { keys: [['↑'], ['↓']], label: 'Move between items (also k / j)' },
            { keys: [['Home'], ['End']], label: 'Jump to first · last item' },
            { keys: [['Enter'], ['Space']], label: 'Open or select the focused item' },
          ]}
        />
      </Stack>
    </Modal>
  );
}
