const { test } = require('node:test');
const assert = require('node:assert/strict');
const { loadSource } = require('./runtime.cjs');

test('POST merges Accept and Content-Type headers', async () => {
  let sent;
  const { createApiClient } = loadSource('src/api/client.ts', {
    fetch: async (_, init) => { sent = init; return new Response('{}'); },
  });
  await createApiClient().predict('AAPL', 'stock').catch(() => {});
  const headers = new Headers(sent.headers);
  assert.equal(headers.get('Accept'), 'application/json');
  assert.equal(headers.get('Content-Type'), 'application/json');
});

test('successful malformed JSON is rejected', async () => {
  const { createApiClient } = loadSource('src/api/client.ts', {
    fetch: async () => new Response('<html>proxy page</html>'),
  });
  await assert.rejects(createApiClient().health(), /invalid JSON/i);
});

test('prediction requests retain a timeout through response body consumption', async () => {
  let cleared = false;
  let budget;
  const { createApiClient } = loadSource('src/api/client.ts', {
    setTimeout: (_, ms) => { budget = ms; return 123; },
    clearTimeout: () => { cleared = true; },
    fetch: async () => ({ ok: true, status: 200, text: async () => {
      assert.equal(cleared, false);
      return 'null';
    } }),
  });
  await assert.rejects(createApiClient().predict('AAPL', 'stock'), /invalid forecast/i);
  assert.ok(budget >= 75_000);
  assert.equal(cleared, true);
});

test('caller cancellation is forwarded', async () => {
  let sentSignal;
  const external = new AbortController();
  const { createApiClient } = loadSource('src/api/client.ts', {
    fetch: async (_, init) => { sentSignal = init.signal; return new Response('null'); },
  });
  const request = createApiClient().predict('AAPL', 'stock', 7, 'ml', 'USD', external.signal);
  external.abort();
  await request.catch(() => {});
  assert.equal(sentSignal.aborted, true);
});

test('demo data respects requested symbol, horizon and last close', () => {
  const { getDemoForecast } = loadSource('src/data/demoAssets.ts');
  const data = getDemoForecast('UNKNOWN', 'stock', 'EUR', 'stat', 30);
  assert.equal(data.symbol, 'UNKNOWN');
  assert.equal(data.horizon_days, 30);
  assert.equal(data.forecast.length, 30);
  assert.equal(data.history.at(-1).close, data.stats.last_close);
  assert.equal(data.source.market_data, 'demo');
  assert.equal(data.currency, 'USD');
});

test('complete forecast responses remain usable', async () => {
  const { getDemoForecast } = loadSource('src/data/demoAssets.ts');
  const expected = getDemoForecast('AAPL', 'stock', 'USD', 'stat', 7);
  const { createApiClient } = loadSource('src/api/client.ts', {
    fetch: async () => Response.json(expected),
  });
  const actual = await createApiClient().predict('AAPL', 'stock', 7, 'stat', 'USD');
  assert.equal(actual.summary.expected_price, expected.summary.expected_price);
  assert.equal(actual.source.market_data, expected.source.market_data);
});

test('incomplete forecast metadata is rejected before rendering', async () => {
  const { getDemoForecast } = loadSource('src/data/demoAssets.ts');
  const corruptions = [
    data => { delete data.source; },
    data => { data.source.data_warnings = [null]; },
    data => { data.summary.trend = {}; },
    data => { data.forecast[0].date = {}; },
    data => { data.forecast[0].lower = data.forecast[0].upper + 1; },
    data => { data.evaluation = { mae: '1.2' }; },
    data => { data.explanation = { narrative: 'Incomplete' }; },
    data => { data.history = []; },
  ];
  for (const corrupt of corruptions) {
    const data = getDemoForecast('AAPL', 'stock', 'USD', 'stat', 7);
    corrupt(data);
    const { createApiClient } = loadSource('src/api/client.ts', {
      fetch: async () => Response.json(data),
    });
    await assert.rejects(createApiClient().predict('AAPL', 'stock'), /invalid forecast/i);
  }
});

test('malformed ticker responses are rejected before entering list state', async () => {
  for (const items of [null, {}, [null], [{ symbol: 'AAPL', name: {} }]]) {
    const { createApiClient } = loadSource('src/api/client.ts', {
      fetch: async () => Response.json({ items, tickers: items }),
    });
    const api = createApiClient();
    await assert.rejects(api.topAssets('stock'), /invalid ticker/i);
    await assert.rejects(api.searchTickers('AAP', 'stock'), /invalid ticker/i);
  }
});
