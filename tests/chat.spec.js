// @ts-check
const { test, expect } = require('@playwright/test');

test.describe('Chat Panel', () => {
  test('loads the main page', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/ULF/i);
  });

  test('shows chat panel by default', async ({ page }) => {
    await page.goto('/');
    const chatPanel = page.locator('#chat-panel');
    await expect(chatPanel).toBeVisible();
  });

  test('has a message input field', async ({ page }) => {
    await page.goto('/');
    const input = page.locator('#message-input');
    await expect(input).toBeVisible();
  });

  test('can create a new conversation', async ({ page }) => {
    await page.goto('/');
    const newBtn = page.locator('#new-chat-btn');
    await expect(newBtn).toBeVisible();
    await newBtn.click();

    // Input should become enabled after conversation is created
    const input = page.locator('#message-input');
    await expect(input).toBeEnabled({ timeout: 5000 });
  });

  test('can switch between panels', async ({ page }) => {
    await page.goto('/');

    // Click translate tab
    const translateTab = page.locator('#translate-tab');
    await translateTab.click();
    await expect(page.locator('#translate-panel')).toBeVisible();
    await expect(page.locator('#chat-panel')).toBeHidden();

    // Click chat tab
    const chatTab = page.locator('#chat-tab');
    await chatTab.click();
    await expect(page.locator('#chat-panel')).toBeVisible();
  });

  test('attach button shows menu with PDF and Image options', async ({ page }) => {
    await page.goto('/');
    const attachBtn = page.locator('#attach-btn');
    await attachBtn.click();

    const menu = page.locator('#attach-menu');
    await expect(menu).toBeVisible();
    await expect(page.locator('#attach-pdf')).toBeVisible();
    await expect(page.locator('#attach-image')).toBeVisible();
  });
});
