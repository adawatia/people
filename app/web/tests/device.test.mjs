import assert from 'node:assert/strict'
import test from 'node:test'
import { formatDeviceLabel } from '../app/utils/device.ts'

test('formatDeviceLabel formats known desktop browsers', () => {
  assert.equal(
    formatDeviceLabel('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'),
    'Chrome on Windows 10/11'
  )
  assert.equal(
    formatDeviceLabel('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'),
    'Edge on Windows 10/11'
  )
  assert.equal(
    formatDeviceLabel('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15'),
    'Safari on macOS'
  )
  assert.equal(
    formatDeviceLabel('Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0'),
    'Firefox on Linux'
  )
})

test('formatDeviceLabel formats mobile devices', () => {
  assert.equal(
    formatDeviceLabel('Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1'),
    'Safari on iPhone'
  )
  assert.equal(
    formatDeviceLabel('Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'),
    'Chrome on Android'
  )
})

test('formatDeviceLabel handles CLI, server and unknown values', () => {
  assert.equal(formatDeviceLabel('node'), 'Node.js (Server / CLI)')
  assert.equal(formatDeviceLabel('node-fetch/1.0'), 'Node.js (Server / CLI)')
  assert.equal(formatDeviceLabel('curl/7.88.1'), 'cURL')
  assert.equal(formatDeviceLabel('PostmanRuntime/7.36.0'), 'Postman')
  assert.equal(formatDeviceLabel(''), 'Unknown device')
  assert.equal(formatDeviceLabel(null), 'Unknown device')
  assert.equal(formatDeviceLabel(undefined), 'Unknown device')
})
