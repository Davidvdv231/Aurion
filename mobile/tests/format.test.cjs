const { test } = require('node:test');
const assert = require('node:assert/strict');
const { loadSource } = require('./runtime.cjs');

const { formatAxisPrice, formatPrice } = loadSource('src/utils/format.ts');

test('sub-cent prices keep significant digits instead of reading as zero', () => {
  assert.equal(formatPrice(0.00001234, 'USD'), '$0.00001234');
  assert.equal(formatAxisPrice(0.0000123, 'USD'), '$0.0000123');
});

test('ordinary prices keep two decimals', () => {
  assert.equal(formatPrice(1234.5, 'USD'), '$1,234.50');
  assert.equal(formatPrice(0, 'USD'), '$0.00');
});
