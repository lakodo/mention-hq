import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  CloseButton,
  Divider,
  Group,
  Kbd,
  Loader,
  Stack,
  Switch,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { IconAlertTriangle, IconBulb, IconRefresh, IconSearch } from '@tabler/icons-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useCatchup, useSyncStatus } from '../api/hooks';
import { NAV_TARGETS } from '../lib/keyboard';
import { formatAgo } from '../lib/time';
import { useGoToMode } from '../shell/GoToModeContext';
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

  // Sources that failed on the last sync (from the sync log the app already polls), so a source
  // that quietly lost its auth is impossible to miss instead of only showing up in the logs.
  const { data: syncLog } = useSyncStatus();
  const failedSources = syncLog?.[0]?.sources.filter((s) => s.error) ?? [];

  const path = location.pathname;
  const isDetail = path.startsWith('/task/');
  const showToolbar = path === '/' || path === '/timeline' || path === '/catchup';
  const isActive = (tabPath: string) => (tabPath === '/' ? path === '/' : path.startsWith(tabPath));

  const goToMode = useGoToMode();
  const letterFor = (tabPath: string) => NAV_TARGETS.find((t) => t.path === tabPath)?.letter;

  const tabButton = (tab: { label: string; path: string }) => {
    const key = letterFor(tab.path);
    return (
      <Button
        key={tab.path}
        size="xs"
        variant={isActive(tab.path) ? 'white' : 'subtle'}
        color={isActive(tab.path) ? 'dark' : 'gray'}
        onClick={() => navigate(tab.path)}
        aria-current={isActive(tab.path) ? 'page' : undefined}
        leftSection={
          // While `g` is armed, show each tab's go-to key right on the tab.
          goToMode && key ? (
            <Kbd style={{ padding: '0 5px', fontSize: 10, lineHeight: 1.4 }}>{key}</Kbd>
          ) : undefined
        }
        rightSection={
          tab.path === '/catchup' && catchupCount > 0 ? (
            // Not `circle`: a fixed-width circle clips a two-digit count to "1..". A pill grows.
            <Badge size="xs" variant="filled" color="pink" px={6}>
              {catchupBadge}
            </Badge>
          ) : undefined
        }
      >
        {tab.label}
      </Button>
    );
  };

  return (
    <Group
      component="header"
      gap="md"
      wrap="nowrap"
      px="lg"
      py="sm"
      style={{
        borderBottom: '1px solid var(--mantine-color-gray-3)',
        background: 'var(--mantine-color-body)',
      }}
    >
      <Stack gap={2} style={{ flexShrink: 0, whiteSpace: 'nowrap' }}>
        <Text
          component={Link}
          to="/welcome"
          fw={700}
          fz="lg"
          c="inherit"
          style={{ textDecoration: 'none', cursor: 'pointer' }}
        >
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

      <Group gap={6} wrap="nowrap" style={{ flexShrink: 0 }}>
        <Tooltip label="Brain dump — capture a thought" withArrow>
          <ActionIcon
            size="lg"
            variant={path.startsWith('/braindump') ? 'filled' : 'light'}
            color="indigo"
            aria-label="Brain dump"
            onClick={() => navigate('/braindump')}
          >
            <IconBulb size={18} />
          </ActionIcon>
        </Tooltip>
        <Group gap={2} p={3} style={{ borderRadius: 8, background: 'var(--mantine-color-gray-1)' }}>
          {PRIMARY_TABS.map(tabButton)}
        </Group>
        <Group gap={2} p={3} style={{ borderRadius: 8, background: 'var(--mantine-color-gray-0)' }}>
          {SECONDARY_TABS.map(tabButton)}
        </Group>
      </Group>

      {failedSources.length > 0 && (
        <Tooltip
          withArrow
          multiline
          w={260}
          label={`${failedSources.map((s) => s.source).join(', ')} couldn't sync — likely needs reconnecting. Open Admin to fix it.`}
        >
          <Button
            size="xs"
            variant="light"
            color="orange"
            leftSection={<IconAlertTriangle size={15} />}
            onClick={() => navigate('/admin')}
            aria-label={`${failedSources.length} source${failedSources.length > 1 ? 's' : ''} need attention`}
            style={{ flexShrink: 0 }}
          >
            {failedSources.length} {failedSources.length === 1 ? 'source' : 'sources'} failing
          </Button>
        </Tooltip>
      )}

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
