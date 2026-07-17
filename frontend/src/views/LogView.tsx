import { Box, Center, Loader, Text } from '@mantine/core';
import { useEffect, useRef } from 'react';
import {
  MONO_FONT,
  TERMINAL_BG,
  TERMINAL_BORDER,
  TERMINAL_DIM,
  TERMINAL_GREEN,
  TERMINAL_MUTED,
  TERMINAL_RED,
  TERMINAL_TEXT,
} from '../constants';
import { useSettings, useSyncStatus } from '../api/hooks';
import { formatClock } from '../lib/time';
import type { SyncLogEntry } from '../types';

function runSummary(entry: SyncLogEntry): string {
  const sources = entry.sources.length;
  return [
    `Synced ${sources} ${sources === 1 ? 'source' : 'sources'}`,
    `${entry.items_fetched} items fetched`,
    `${entry.items_added} new`,
    `${entry.proposals} proposed`,
    `${entry.duration_seconds.toFixed(1)}s`,
  ].join(' · ');
}

interface LineProps {
  color: string;
  children: string;
}

function Line({ color, children }: LineProps) {
  return (
    <Text component="div" style={{ color, fontFamily: MONO_FONT, fontSize: 13, lineHeight: 1.7 }}>
      {children}
    </Text>
  );
}

function promptFor(appName: string): string {
  const slug = appName.trim().toLowerCase().replace(/\s+/g, '-') || 'hq';
  return `${slug}:~$`;
}

export function LogView() {
  const { data: entries, isLoading } = useSyncStatus();
  const { data: settings } = useSettings();
  const prompt = promptFor(settings?.app_name ?? 'hq');

  const scrollRef = useRef<HTMLDivElement>(null);
  // The newest run is at the bottom, so open at the end like a shell rather than the top.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries]);

  if (isLoading) {
    return (
      <Center style={{ flex: 1, background: TERMINAL_BG }}>
        <Loader />
      </Center>
    );
  }

  // Oldest first, so the newest run sits just above the cursor like a real shell.
  const runs = [...(entries ?? [])].reverse();

  return (
    <Box
      ref={scrollRef}
      style={{
        flex: 1,
        overflow: 'auto',
        background: TERMINAL_BG,
        padding: '20px 24px',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      <Box
        style={{
          color: TERMINAL_MUTED,
          fontFamily: MONO_FONT,
          fontSize: 12,
          marginBottom: 12,
          borderBottom: `1px solid ${TERMINAL_BORDER}`,
          paddingBottom: 10,
        }}
      >
        {prompt}
      </Box>

      <Box style={{ display: 'flex', flexDirection: 'column' }}>
        {runs.length === 0 && <Line color={TERMINAL_DIM}>No syncs yet.</Line>}

        {runs.map((entry) => {
          const ts = formatClock(entry.started_at);
          return (
            <Box key={entry.id} data-testid="log-run">
              <Line color={TERMINAL_DIM}>{`[${ts}] $ hq sync --all`}</Line>
              <Line color={entry.error ? TERMINAL_RED : TERMINAL_GREEN}>
                {`[${ts}] ${runSummary(entry)}`}
              </Line>
              {entry.sources.map((source) => (
                <Line key={source.source} color={source.error ? TERMINAL_RED : TERMINAL_MUTED}>
                  {`[${ts}]   ${source.source}: ${
                    source.error
                      ? `error — ${source.error}`
                      : source.configured
                        ? `${source.items_fetched} items`
                        : 'not configured'
                  }`}
                </Line>
              ))}
              {entry.error && <Line color={TERMINAL_RED}>{`[${ts}] error: ${entry.error}`}</Line>}
            </Box>
          );
        })}

        <Box
          style={{
            display: 'flex',
            gap: 8,
            color: TERMINAL_TEXT,
            fontFamily: MONO_FONT,
            fontSize: 13,
            marginTop: 4,
          }}
        >
          <span>{prompt}</span>
          <span className="hq-cursor">█</span>
        </Box>
      </Box>
    </Box>
  );
}
