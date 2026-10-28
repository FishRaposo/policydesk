import {describe, expect, it} from 'vitest';
import {isLocalRuntime} from '../src/local';

describe('local runtime boundary', () => {
  it('recognizes only the server-injected local marker', () => {
    const marked = {querySelector: () => ({getAttribute: () => 'local'})} as unknown as Document;
    expect(isLocalRuntime(marked)).toBe(true);
    expect(isLocalRuntime({querySelector: () => null} as unknown as Document)).toBe(false);
    expect(isLocalRuntime({querySelector: () => ({getAttribute: () => 'public'})} as unknown as Document)).toBe(false);
  });
});
