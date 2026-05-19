import { test, expect } from "@playwright/test";
import { createTestApi, loginAsDefault } from "./helpers";
import type { TestApiClient } from "./fixtures";

test.describe("Comments", () => {
  let api: TestApiClient;
  let issueId: string;

  test.beforeEach(async ({ page }) => {
    api = await createTestApi();
    const issue = await api.createIssue("E2E Comment Test " + Date.now());
    issueId = issue.id;
    const workspaceSlug = await loginAsDefault(page);
    await page.goto(`/${workspaceSlug}/issues/${issueId}`);
  });

  test.afterEach(async () => {
    await api.cleanup();
  });

  test("can add a comment on an issue", async ({ page }) => {
    await expect(page.locator("text=Properties")).toBeVisible();

    const commentText = "E2E comment " + Date.now();
    const commentInput = page.getByTestId("comment-input").locator(".ProseMirror");
    await expect(commentInput).toBeVisible({ timeout: 10000 });
    await commentInput.click();
    await page.keyboard.type(commentText);

    await page.getByRole("button", { name: "Submit comment" }).click();

    // Comment should appear in the activity section
    await expect(page.locator('[id^="comment-"]').getByText(commentText)).toBeVisible({
      timeout: 5000,
    });
  });

  test("comment composer is available but cannot submit while empty", async ({ page }) => {
    await expect(page.locator("text=Properties")).toBeVisible();

    await expect(page.getByTestId("comment-input")).toBeVisible({ timeout: 10000 });
    const submitBtn = page.getByRole("button", { name: "Submit comment" });
    await expect(submitBtn).toBeVisible();
    await expect(submitBtn).toBeDisabled();
  });
});
