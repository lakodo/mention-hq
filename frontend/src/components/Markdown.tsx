import { TypographyStylesProvider } from '@mantine/core';
import type { ComponentPropsWithoutRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Links open in a new tab; a click on one must not bubble to a click-to-edit wrapper around it.
function MarkdownLink(props: ComponentPropsWithoutRef<'a'>) {
  return (
    <a {...props} target="_blank" rel="noreferrer noopener" onClick={(e) => e.stopPropagation()} />
  );
}

/**
 * Render Markdown (GFM: tables, task lists, strikethrough, autolinks) as styled content. Raw HTML
 * in the source is not rendered — react-markdown escapes it — so untrusted text can't inject markup.
 */
export function Markdown({ children }: { children: string }) {
  return (
    <TypographyStylesProvider fz="sm" p={0} m={0}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: MarkdownLink }}>
        {children}
      </ReactMarkdown>
    </TypographyStylesProvider>
  );
}
