import { expect, type Locator, type Page } from '@playwright/test';

/**
 * Monaco 是按需加载的：textarea 出现得比视图就绪早，这时打字会被整段丢弃
 * （草稿仍是“已保存”，保存按钮保持禁用）。这里等到视图与 monaco 实例都就绪。
 */
export async function waitEditorReady(page: Page, input: Locator) {
  await expect(input).toBeVisible({ timeout: 150000 });
  // 视图行里有实际文字才算就绪（只看 textarea 出现会过早）
  await page.waitForFunction(
    () => (document.querySelector('.monaco-editor .view-lines')?.textContent ?? '').trim().length > 0,
    undefined,
    { timeout: 150000 },
  );
  await input.focus();
  await expect(input).toBeFocused();
}