const { test } = require('node:test');
const assert = require('node:assert/strict');
const { loadSource } = require('./runtime.cjs');
const { parseWatchlist, createOrderedWriter } = loadSource('src/storage/watchlist.ts');

test('watchlist rejects malformed records and deduplicates per market', () => {
  const item = { symbol: 'AAPL', name: 'Apple', assetType: 'stock', addedAt: '2026-09-08' };
  assert.equal(parseWatchlist('{}').length, 0);
  const data = parseWatchlist(JSON.stringify([null, {}, item, item, { ...item, assetType: 'crypto' }]));
  assert.equal(data.length, 2);
});

test('writes remain ordered and continue after a failed save', async () => {
  const calls = [];
  let release;
  const write = createOrderedWriter(async value => {
    calls.push(value);
    if (value === 'first') {
      await new Promise(resolve => { release = resolve; });
      throw new Error('quota');
    }
  });
  const first = write('first');
  const rejection = assert.rejects(first, /quota/);
  const second = write('second');
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(calls, ['first']);
  release();
  await Promise.all([rejection, second]);
  assert.deepEqual(calls, ['first', 'second']);
});
