import {
  Anchor,
  Button,
  Divider,
  Group,
  Loader,
  Stack,
  Switch,
  Text,
  TextInput,
} from '@mantine/core';
import { IconRefresh, IconSearch } from '@tabler/icons-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { formatAgo } from '../lib/time';
import { useHq } from '../shell/HqContext';

const TABS = [
  { label: 'Board', path: '/' },
  { label: 'Timeline', path: '/timeline' },
  { label: 'Catch-up', path: '/catchup' },
  { label: 'Log', path: '/log' },
  { label: 'Admin', path: '/admin' },
];

export function Header() {
  const location = useLocation();
  const navigate = useNavigate();
  const {
    appName,
    query,
    setQuery,
    autoSync,
    toggleAutoSync,
    lastSync,
    syncing,
    runSync,
    taskCount,
    itemCount,
  } = useHq();

  const path = location.pathname;
  const isDetail = path.startsWith('/task');
  const showToolbar = path === '/' || path === '/timeline' || path === '/catchup';
  const isActive = (tabPath: string) => (tabPath === '/' ? path === '/' : path.startsWith(tabPath));

  return (
    <Group
      component="header"
      gap="xl"
      wrap="nowrap"
      px="lg"
      py="sm"
      style={{
        borderBottom: '1px solid var(--mantine-color-gray-3)',
        background: 'var(--mantine-color-body)',
      }}
    >
      <Stack gap={2} style={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
        <Text fw={700} fz="lg">
          {appName}
        </Text>
        {isDetail ? (
          <Anchor component={Link} to="/" fz="xs" fw={600}>
            ← Back to board
          </Anchor>
        ) : (
          <Text fz="xs" c="dimmed">
            {itemCount} {itemCount === 1 ? 'item' : 'items'} across {taskCount}{' '}
            {taskCount === 1 ? 'task' : 'tasks'}
          </Text>
        )}
      </Stack>

      <Group gap={4} p={3} style={{ borderRadius: 8, background: 'var(--mantine-color-gray-1)' }}>
        {TABS.map((tab) => (
          <Button
            key={tab.path}
            size="xs"
            variant={isActive(tab.path) ? 'white' : 'subtle'}
            color={isActive(tab.path) ? 'dark' : 'gray'}
            onClick={() => navigate(tab.path)}
          >
            {tab.label}
          </Button>
        ))}
      </Group>

      {showToolbar && (
        <>
          <TextInput
            placeholder="Search… try bucket:infra or tag:ci"
            aria-label="Search"
            leftSection={<IconSearch size={14} />}
            value={query}
            onChange={(e) => setQuery(e.currentTarget.value)}
            w={280}
            style={{ flexShrink: 1 }}
          />

          <Group
            gap="md"
            wrap="nowrap"
            ml="auto"
            px="sm"
            py={6}
            style={{
              border: '1px solid var(--mantine-color-gray-3)',
              borderRadius: 10,
              background: 'var(--mantine-color-gray-0)',
              flexShrink: 0,
            }}
          >
            <Text fz="xs" c="dimmed" style={{ whiteSpace: 'nowrap' }}>
              {lastSync ? `Synced ${formatAgo(lastSync)}` : 'Never synced'}
            </Text>
            <Divider orientation="vertical" />
            <Switch
              size="sm"
              checked={autoSync}
              onChange={toggleAutoSync}
              label="Auto-sync"
              labelPosition="left"
              styles={{
                label: {
                  fontSize: 'var(--mantine-font-size-xs)',
                  color: 'var(--mantine-color-dimmed)',
                },
              }}
            />
            <Button
              size="xs"
              onClick={runSync}
              disabled={syncing}
              leftSection={syncing ? <Loader size={12} color="white" /> : <IconRefresh size={14} />}
            >
              {syncing ? 'Syncing…' : 'Sync'}
            </Button>
          </Group>
        </>
      )}
    </Group>
  );
}
