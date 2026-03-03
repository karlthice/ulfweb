#!/usr/bin/env node
/**
 * Vault Tutorial Screenshot Capture
 *
 * Standalone Playwright script that logs in, creates sample vault data,
 * and captures 10 screenshots for the Vault Tutorial PDF.
 *
 * Usage:
 *   node tests/vault-tutorial-screenshots.js
 *
 * Prerequisites:
 *   npm install playwright    (or npx playwright install chromium)
 *   ULF Web running on http://localhost:8000
 */

const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const BASE_URL = process.env.ULFWEB_URL || 'http://localhost:8000';
const USERNAME = process.env.ULFWEB_USER || 'karlth';
const PASSWORD = process.env.ULFWEB_PASS || 'golf91';
const SCREENSHOT_DIR = path.join(__dirname, '..', 'docs', 'screenshots');

async function main() {
  // Ensure output directory exists
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 800 },
  });
  const page = await context.newPage();

  try {
    // ── Login ──────────────────────────────────────────────────────────
    console.log('Logging in...');
    await page.goto(`${BASE_URL}/login`);
    await page.fill('#username', USERNAME);
    await page.fill('#password', PASSWORD);
    await page.click('#login-btn');
    await page.waitForSelector('#chat-panel', { timeout: 10000 });
    console.log('Login successful.');

    // ── Clean up existing CASE-001 via API (idempotent) ───────────────
    console.log('Cleaning up existing CASE-001 if present...');
    const cookies = await context.cookies();
    const cookieHeader = cookies.map(c => `${c.name}=${c.value}`).join('; ');
    const casesResp = await page.evaluate(async () => {
      const resp = await fetch('/api/v1/vault/cases');
      return resp.json();
    });
    if (Array.isArray(casesResp)) {
      for (const c of casesResp) {
        if (c.identifier === 'CASE-001') {
          console.log(`  Deleting existing case ${c.id}...`);
          await page.evaluate(async (caseId) => {
            await fetch(`/api/v1/vault/cases/${caseId}`, { method: 'DELETE' });
          }, c.id);
        }
      }
    }

    // ── Screenshot 1: Vault tab ───────────────────────────────────────
    console.log('1/10  Vault tab...');
    await page.click('#vault-tab');
    await page.waitForSelector('#vault-case-list', { timeout: 5000 });
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '01-vault-tab.png'),
    });

    // ── Screenshot 2: New case form ───────────────────────────────────
    console.log('2/10  New case form...');
    await page.click('#vault-new-case-btn');
    await page.waitForSelector('#vault-create-form', { timeout: 3000 });
    await page.fill('#vault-new-identifier', 'CASE-001');
    await page.fill('#vault-new-name', 'Smith Investigation');
    await page.fill('#vault-new-description', 'Investigation into the Smith incident reported on 15 Feb 2026.');
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '02-new-case-form.png'),
    });

    // ── Screenshot 3: Case list after creation ────────────────────────
    console.log('3/10  Case list...');
    await page.click('#vault-create-submit');
    await page.waitForTimeout(1000);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '03-case-list.png'),
    });

    // ── Screenshot 4: Case detail view ────────────────────────────────
    console.log('4/10  Case detail...');
    // Click the newly created case in the list
    const caseItem = page.locator('.vault-case-item', { hasText: 'CASE-001' });
    await caseItem.first().click();
    await page.waitForSelector('#vault-record-list', { timeout: 5000 });
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '04-case-detail.png'),
    });

    // ── Screenshot 5: Add text record form ────────────────────────────
    console.log('5/10  Add text record form...');
    await page.click('#vault-add-record-btn');
    await page.waitForSelector('#vault-add-record-form', { timeout: 3000 });
    await page.fill('#vault-record-title', 'Initial Interview Notes');
    await page.fill('#vault-record-content',
      'Interviewed John Smith at 10:00 AM on 15 Feb 2026.\n' +
      'Subject stated he was at home during the evening of 14 Feb.\n' +
      'No witnesses corroborated this account.'
    );
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '05-add-text-record.png'),
    });

    // ── Screenshot 6: Records populated ───────────────────────────────
    console.log('6/10  Records populated...');
    await page.click('#vault-record-submit');
    await page.waitForTimeout(1500);

    // Add a second record
    await page.click('#vault-add-record-btn');
    await page.waitForSelector('#vault-add-record-form', { timeout: 3000 });
    await page.fill('#vault-record-title', 'Surveillance Report');
    await page.fill('#vault-record-content',
      'Subject observed leaving residence at 18:45 on 14 Feb 2026.\n' +
      'Returned at 22:30. Vehicle plate: ABC-123.'
    );
    await page.click('#vault-record-submit');
    await page.waitForTimeout(1500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '06-records-populated.png'),
    });

    // ── Screenshot 7: Starred record ──────────────────────────────────
    console.log('7/10  Starred record...');
    const starBtn = page.locator('.vault-star-btn').first();
    await starBtn.click();
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '07-starred-record.png'),
    });

    // ── Screenshot 8: Export menu ─────────────────────────────────────
    console.log('8/10  Export menu...');
    await page.click('#vault-export-btn');
    await page.waitForSelector('#vault-export-menu', { timeout: 3000 });
    await page.waitForTimeout(300);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '08-export-menu.png'),
    });
    // Close the menu by pressing Escape
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);

    // ── Screenshot 9: Chat @mention autocomplete ──────────────────────
    console.log('9/10  Chat @mention autocomplete...');
    await page.click('#chat-tab');
    await page.waitForSelector('#chat-panel', { timeout: 5000 });
    // Create a new conversation so the input is enabled
    await page.click('#new-chat-btn');
    await page.waitForSelector('#message-input:not([disabled])', { timeout: 5000 });
    await page.waitForTimeout(500);
    await page.click('#message-input');
    await page.type('#message-input', '@Smith', { delay: 80 });
    await page.waitForSelector('#mention-dropdown', { timeout: 3000 });
    await page.waitForTimeout(400);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '09-chat-at-mention.png'),
    });

    // ── Screenshot 10: Completed @mention in input ────────────────────
    console.log('10/10 Chat with completed @mention...');
    const mentionItem = page.locator('.mention-item').first();
    await mentionItem.click();
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, '10-chat-with-mention.png'),
    });

    console.log(`\nAll 10 screenshots saved to ${SCREENSHOT_DIR}`);
  } catch (err) {
    console.error('Screenshot capture failed:', err.message);
    // Save a debug screenshot on failure
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'debug-failure.png'),
    });
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
}

main();
