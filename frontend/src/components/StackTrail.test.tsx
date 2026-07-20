import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Providers } from '../test/utils';
import { StackTrail } from './StackTrail';

describe('StackTrail', () => {
  it('draws the whole downstack chain of a stacked branch', () => {
    render(
      <Providers>
        <StackTrail stack={['feat-a', 'feat-b', 'feat-c']} />
      </Providers>,
    );

    for (const branch of ['feat-a', 'feat-b', 'feat-c']) {
      expect(screen.getByText(branch)).toBeInTheDocument();
    }
  });

  it('renders nothing for a branch that sits on the trunk alone', () => {
    render(
      <Providers>
        <StackTrail stack={['feat-a']} />
      </Providers>,
    );

    expect(screen.queryByText('feat-a')).not.toBeInTheDocument();
  });
});
