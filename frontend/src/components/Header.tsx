import {
  ActionIcon,
  Anchor,
  Badge,
  Box,
  Button,
  CloseButton,
  Divider,
  Group,
  Loader,
  Stack,
  Switch,
  Text,
  TextInput,
  Tooltip,
} from '@mantine/core';
import { IconBulb, IconRefresh, IconSearch } from '@tabler/icons-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useCatchup } from '../api/hooks';
import { formatAgo } from '../lib/time';
import { useRovingFocus } from '../lib/useRovingFocus';
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

  const navKeys = useRovingFocus<HTMLDivElement>({ orientation: 'horizontal' });

  const tabButton = (tab: { label: string; path: string }) => (
    <Button
      key={tab.path}
      size="xs"
      variant={isActive(tab.path) ? 'white' : 'subtle'}
      color={isActive(tab.path) ? 'dark' : 'gray'}
      onClick={() => navigate(tab.path)}
      data-roving-item
      aria-current={isActive(tab.path) ? 'page' : undefined}
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
        <Box
          role="toolbar"
          aria-label="Views"
          ref={navKeys.ref}
          onKeyDown={navKeys.onKeyDown}
          style={{ display: 'flex', gap: 6 }}
        >
          <Group
            gap={2}
            p={3}
            style={{ borderRadius: 8, background: 'var(--mantine-color-gray-1)' }}
          >
            {PRIMARY_TABS.map(tabButton)}
          </Group>
          <Group
            gap={2}
            p={3}
            style={{ borderRadius: 8, background: 'var(--mantine-color-gray-0)' }}
          >
            {SECONDARY_TABS.map(tabButton)}
          </Group>
        </Box>
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
