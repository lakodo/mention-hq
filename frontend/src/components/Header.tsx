import {
  Anchor,
  Badge,
  Button,
  CloseButton,
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
import { useCatchup } from '../api/hooks';
import { formatAgo } from '../lib/time';
import { useHq } from '../shell/HqContext';

// The everyday flow leads; the reference views sit in a second group.
const PRIMARY_TABS = [
  { label: 'Catch-up', path: '/catchup' },
  { label: 'Tasks', path: '/task' },
  { label: 'Buckets', path: '/' },
];
const SECONDARY_TABS = [
  { label: 'Timeline', path: '/timeline' },
  { label: 'People', path: '/people' },
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

  const { data: catchupItems } = useCatchup();
  const catchupCount = catchupItems?.length ?? 0;
  const catchupBadge = catchupCount > 99 ? '99+' : String(catchupCount);

  const path = location.pathname;
  const isDetail = path.startsWith('/task/');
  const showToolbar = path === '/' || path === '/timeline' || path === '/catchup';
  const isActive = (tabPath: string) => (tabPath === '/' ? path === '/' : path.startsWith(tabPath));

  const tabButton = (tab: { label: string; path: string }) => (
    <Button
      key={tab.path}
      size="xs"
      variant={isActive(tab.path) ? 'white' : 'subtle'}
      color={isActive(tab.path) ? 'dark' : 'gray'}
      onClick={() => navigate(tab.path)}
      rightSection={
        tab.path === '/catchup' && catchupCount > 0 ? (
          <Badge size="xs" circle variant="filled" color="pink">
            {catchupBadge}
          </Badge>
        ) : undefined
      }
    >
      {tab.label}
    </Button>
  );

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
          <Anchor component={Link} to="/task" fz="xs" fw={600}>
            ← All tasks
          </Anchor>
        ) : (
          <Text fz="xs" c="dimmed">
            {itemCount} {itemCount === 1 ? 'item' : 'items'} across {taskCount}{' '}
            {taskCount === 1 ? 'task' : 'tasks'}
          </Text>
        )}
      </Stack>

      <Group gap={8} wrap="nowrap">
        <Group gap={4} p={3} style={{ borderRadius: 8, background: 'var(--mantine-color-gray-1)' }}>
          {PRIMARY_TABS.map(tabButton)}
        </Group>
        <Group gap={4} p={3} style={{ borderRadius: 8, background: 'var(--mantine-color-gray-0)' }}>
          {SECONDARY_TABS.map(tabButton)}
        </Group>
      </Group>

      {showToolbar && (
        <>
          <TextInput
            placeholder="Search… try bucket:infra or tag:ci"
            aria-label="Search"
            leftSection={<IconSearch size={14} />}
            rightSection={
              query ? (
                <CloseButton size="sm" aria-label="Clear search" onClick={() => setQuery('')} />
              ) : null
            }
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
