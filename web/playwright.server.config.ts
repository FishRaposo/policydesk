import {defineConfig} from '@playwright/test';
import {resolve} from 'node:path';

const python=process.env.POLICYDESK_TEST_PYTHON??resolve(import.meta.dirname,'..','.venv',process.platform==='win32'?'Scripts':'bin',process.platform==='win32'?'python.exe':'python');
export default defineConfig({
  testDir:'./integration',
  outputDir:'../.runtime/browser-server-results',
  fullyParallel:false,
  workers:1,
  retries:0,
  timeout:60000,
  expect:{timeout:45000},
  reporter:'list',
  use:{baseURL:'http://127.0.0.1:8765/policydesk/',channel:process.env.CI?undefined:'msedge',trace:'retain-on-failure'},
  webServer:{command:`"${python}" ../tests/local_http_fixture.py`,url:'http://127.0.0.1:8765/policydesk/',reuseExistingServer:false,timeout:30000},
});
