import { test, expect, type Page } from "@playwright/test";
import { createTestApi, loginAsDefault } from "./helpers";
import type { TestApiClient } from "./fixtures";

async function expectNoRawJsonPage(page: Page) {
  const text = (await page.locator("body").innerText()).trim();
  expect(text).not.toMatch(/^\s*[\[{].*[\]}]\s*$/s);
}

function projectRow(page: Page, projectId: string) {
  return page.getByTestId(`project-row-${projectId}`);
}

test.describe("Projects", () => {
  let api: TestApiClient;
  let workspaceSlug: string;

  test.beforeEach(async ({ page }) => {
    api = await createTestApi();
    workspaceSlug = await loginAsDefault(page);
  });

  test.afterEach(async () => {
    if (api) {
      await api.cleanup();
    }
  });

  test("lists an API-seeded project with the project count", async ({ page }) => {
    const project = await api.createProject("E2E Seeded Project " + Date.now(), {
      priority: "medium",
    });
    const list = await api.listProjects();

    await page.goto(`/${workspaceSlug}/projects`);

    await expect(projectRow(page, project.id)).toContainText(project.title);
    await expect(page.getByTestId("projects-count")).toHaveText(String(list.projects.length));
    await expectNoRawJsonPage(page);
  });

  test("creates a project, opens detail, and shows it after returning to the list", async ({ page }) => {
    await page.goto(`/${workspaceSlug}/projects`);

    await page.getByRole("button", { name: "New project" }).click();
    const title = "E2E Created Project " + Date.now();
    await page.getByRole("textbox", { name: "Project title" }).fill(title);
    await page.getByRole("button", { name: "No priority" }).click();
    await page.getByRole("menuitem", { name: "High" }).click();

    const createResponsePromise = page.waitForResponse(
      (response) => response.url().includes("/api/projects") &&
        response.request().method() === "POST" &&
        response.status() === 201,
    );
    await page.getByRole("button", { name: "Create Project" }).click();
    const createResponse = await createResponsePromise;
    const created = await createResponse.json();
    api.trackProject(created.id);

    await page.waitForURL(new RegExp(`/${workspaceSlug}/projects/${created.id}$`));
    await expect(page.getByText(title).first()).toBeVisible();

    await page.goto(`/${workspaceSlug}/projects`);
    await expect(projectRow(page, created.id)).toContainText(title);
    await expect(projectRow(page, created.id)).toContainText("High");
    await expect(page.getByTestId("projects-count")).not.toHaveText("0");
    await expectNoRawJsonPage(page);
  });

  test("keeps the create modal safe when the project API fails", async ({ page }) => {
    await page.route("**/api/projects", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "forced project create failure" }),
        });
        return;
      }
      await route.fallback();
    });

    await page.goto(`/${workspaceSlug}/projects`);
    await page.getByRole("button", { name: "New project" }).click();
    await page.getByRole("textbox", { name: "Project title" }).fill("E2E Failed Project " + Date.now());

    const failedCreatePromise = page.waitForResponse(
      (response) => response.url().includes("/api/projects") &&
        response.request().method() === "POST" &&
        response.status() === 500,
    );
    await page.getByRole("button", { name: "Create Project" }).click();
    await failedCreatePromise;

    await expect(page).toHaveURL(new RegExp(`/${workspaceSlug}/projects$`));
    await expect(page.getByText("Failed to create project")).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Project title" })).toBeVisible();
    await expectNoRawJsonPage(page);
  });

  test("updates project priority and status from the list and persists after reload", async ({ page }) => {
    const project = await api.createProject("E2E Updated Project " + Date.now(), {
      priority: "medium",
      status: "planned",
    });

    await page.goto(`/${workspaceSlug}/projects`);
    const row = projectRow(page, project.id);
    await expect(row).toContainText(project.title);

    const priorityResponsePromise = page.waitForResponse(
      (response) => response.url().includes(`/api/projects/${project.id}`) &&
        response.request().method() === "PUT" &&
        response.status() === 200,
    );
    await row.getByRole("button", { name: /Medium/ }).click();
    await page.getByRole("menuitem", { name: "Urgent" }).click();
    await priorityResponsePromise;
    await expect(row.getByTestId("project-row-priority")).toHaveText("Urgent");

    const statusResponsePromise = page.waitForResponse(
      (response) => response.url().includes(`/api/projects/${project.id}`) &&
        response.request().method() === "PUT" &&
        response.status() === 200,
    );
    await row.getByRole("button", { name: /Planned/ }).click();
    await page.getByRole("menuitem", { name: "In Progress" }).click();
    await statusResponsePromise;
    await expect(row.getByTestId("project-row-status")).toHaveText("In Progress");

    await page.reload();
    const reloadedRow = projectRow(page, project.id);
    await expect(reloadedRow.getByTestId("project-row-priority")).toHaveText("Urgent");
    await expect(reloadedRow.getByTestId("project-row-status")).toHaveText("In Progress");
  });

  test("deletes a project from the browser and removes it from the list", async ({ page }) => {
    const project = await api.createProject("E2E Deleted Project " + Date.now());
    const beforeDelete = await api.listProjects();

    await page.goto(`/${workspaceSlug}/projects/${project.id}`);
    await expect(page.getByText(project.title).first()).toBeVisible();
    await page.getByRole("button", { name: "Project actions" }).click();
    await page.getByRole("menuitem", { name: "Delete project" }).click();

    const deleteResponsePromise = page.waitForResponse(
      (response) => response.url().includes(`/api/projects/${project.id}`) &&
        response.request().method() === "DELETE" &&
        response.status() === 204,
    );
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await deleteResponsePromise;

    await page.waitForURL(new RegExp(`/${workspaceSlug}/projects$`));
    await expect(page.getByTestId(`project-row-${project.id}`)).toHaveCount(0);
    if (beforeDelete.projects.length > 1) {
      await expect(page.getByTestId("projects-count")).toHaveText(String(beforeDelete.projects.length - 1));
    } else {
      await expect(page.getByText("No projects yet")).toBeVisible();
    }
  });
});
