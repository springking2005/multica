import { type Page } from "@playwright/test";
import { TestApiClient } from "./fixtures";

const DEFAULT_E2E_NAME = "E2E User";
const DEFAULT_E2E_EMAIL = "e2e@multica.ai";
const DEFAULT_E2E_WORKSPACE = "e2e-workspace";

/**
 * Log in as the default E2E user and ensure the workspace exists first.
 * Authenticates through the E2E fixture client, then injects the token into
 * localStorage so the browser session is authenticated.
 *
 * Returns the E2E workspace slug so callers can build workspace-scoped URLs.
 */
export async function loginAsDefault(page: Page): Promise<string> {
  const api = new TestApiClient();
  await api.login(DEFAULT_E2E_EMAIL, DEFAULT_E2E_NAME);
  const workspace = await api.ensureWorkspace(
    "E2E Workspace",
    DEFAULT_E2E_WORKSPACE,
  );
  await api.dismissStarterContent(workspace.id);

  const token = api.getToken();
  await page.addInitScript((auth) => {
    window.localStorage.setItem("multica_token", auth.token);
    window.localStorage.setItem("multica:chat:isOpen", "false");
    window.localStorage.setItem("multica_create_mode", JSON.stringify({ state: { lastMode: "manual" }, version: 0 }));
  }, { token });
  await page.goto(`/${workspace.slug}/issues`);
  await page.waitForURL("**/issues", { timeout: 10000 });
  return workspace.slug;
}

/**
 * Create a TestApiClient logged in as the default E2E user.
 * Call api.cleanup() in afterEach to remove test data created during the test.
 */
export async function createTestApi(): Promise<TestApiClient> {
  const api = new TestApiClient();
  await api.login(DEFAULT_E2E_EMAIL, DEFAULT_E2E_NAME);
  const workspace = await api.ensureWorkspace("E2E Workspace", DEFAULT_E2E_WORKSPACE);
  await api.dismissStarterContent(workspace.id);
  return api;
}

export async function openWorkspaceMenu(page: Page) {
  await page.getByRole("button", { name: /E2E Workspace|Renamed WS/ }).first().click();
  await page.getByRole("menu").waitFor({ state: "visible" });
}
