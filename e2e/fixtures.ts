/**
 * TestApiClient — lightweight API helper for E2E test data setup/teardown.
 *
 * Uses raw fetch so E2E tests have zero build-time coupling to the web app.
 */

import "./env";
import crypto from "crypto";
import pg from "pg";

// `||` (not `??`) so an empty `NEXT_PUBLIC_API_URL=` in .env still falls
// back to localhost. dotenv sets unset-vs-empty both as "" — treating them
// the same matches user intent.
const API_BASE = process.env.NEXT_PUBLIC_API_URL || `http://localhost:${process.env.PORT || "8080"}`;
const DATABASE_URL = process.env.DATABASE_URL ?? "postgres://multica:multica@localhost:5432/multica?sslmode=disable";
const JWT_SECRET = process.env.JWT_SECRET || "multica-dev-secret-change-in-production";

interface TestWorkspace {
  id: string;
  name: string;
  slug: string;
}

interface TestProject {
  id: string;
  title: string;
  [key: string]: unknown;
}

interface ListProjectsResponse {
  projects: TestProject[];
  total?: number;
}

async function findUserByEmail(client: pg.Client, email: string) {
  const result = await client.query(
    `SELECT id, email, name FROM "user" WHERE email = $1`,
    [email],
  );
  return result.rows[0] as { id: string; email: string; name: string } | undefined;
}

function base64Url(data: string) {
  return Buffer.from(data)
    .toString("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
}

function signJwt(payload: Record<string, unknown>) {
  const header = base64Url(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const body = base64Url(JSON.stringify(payload));
  const signature = crypto
    .createHmac("sha256", JWT_SECRET)
    .update(`${header}.${body}`)
    .digest("base64")
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");
  return `${header}.${body}.${signature}`;
}

export class TestApiClient {
  private token: string | null = null;
  private workspaceSlug: string | null = null;
  private workspaceId: string | null = null;
  private createdIssueIds: string[] = [];
  private createdProjectIds: string[] = [];

  async login(email: string, name: string) {
    const client = new pg.Client(DATABASE_URL);
    await client.connect();
    try {
      const normalizedEmail = email.toLowerCase().trim();
      let user = await findUserByEmail(client, normalizedEmail);
      if (!user) {
        const result = await client.query(
          `INSERT INTO "user" (email, name, onboarded_at, starter_content_state)
           VALUES ($1, $2, now(), 'dismissed')
           ON CONFLICT (email) DO UPDATE SET
             name = EXCLUDED.name,
             onboarded_at = COALESCE("user".onboarded_at, EXCLUDED.onboarded_at),
             starter_content_state = COALESCE("user".starter_content_state, EXCLUDED.starter_content_state)
           RETURNING id, email, name`,
          [normalizedEmail, name],
        );
        user = result.rows[0];
      } else if (name && user.name !== name) {
        const result = await client.query(
          `UPDATE "user"
           SET name = $2, onboarded_at = COALESCE(onboarded_at, now()),
               starter_content_state = COALESCE(starter_content_state, 'dismissed')
           WHERE email = $1
           RETURNING id, email, name`,
          [normalizedEmail, name],
        );
        user = result.rows[0];
      }

      const now = Math.floor(Date.now() / 1000);
      this.token = signJwt({
        sub: user.id,
        email: user.email,
        name: user.name,
        exp: now + 30 * 24 * 60 * 60,
        iat: now,
      });

      await client.query("DELETE FROM verification_code WHERE email = $1", [normalizedEmail]);
      return { token: this.token, user };
    } finally {
      await client.end();
    }
  }

  async getWorkspaces(): Promise<TestWorkspace[]> {
    const res = await this.authedFetch("/api/workspaces");
    return res.json();
  }

  setWorkspaceId(id: string) {
    this.workspaceId = id;
  }

  setWorkspaceSlug(slug: string) {
    this.workspaceSlug = slug;
  }

  async ensureWorkspace(name = "E2E Workspace", slug = "e2e-workspace") {
    const workspaces = await this.getWorkspaces();
    const workspace = workspaces.find((item) => item.slug === slug) ?? workspaces[0];
    if (workspace) {
      this.workspaceId = workspace.id;
      this.workspaceSlug = workspace.slug;
      return workspace;
    }

    const res = await this.authedFetch("/api/workspaces", {
      method: "POST",
      body: JSON.stringify({ name, slug }),
    });
    if (res.ok) {
      const created = (await res.json()) as TestWorkspace;
      this.workspaceId = created.id;
      this.workspaceSlug = created.slug;
      return created;
    }

    const refreshed = await this.getWorkspaces();
    const created = refreshed.find((item) => item.slug === slug) ?? refreshed[0];
    if (created) {
      this.workspaceId = created.id;
      this.workspaceSlug = created.slug;
      return created;
    }

    throw new Error(`Failed to ensure workspace ${slug}: ${res.status} ${res.statusText}`);
  }

  async listProjects(): Promise<ListProjectsResponse> {
    const res = await this.authedFetch("/api/projects");
    if (!res.ok) {
      throw new Error(`list projects failed: ${res.status} ${await res.text()}`);
    }
    return res.json();
  }

  async createProject(title: string, opts?: Record<string, unknown>): Promise<TestProject> {
    const res = await this.authedFetch("/api/projects", {
      method: "POST",
      body: JSON.stringify({ title, ...opts }),
    });
    if (!res.ok) {
      throw new Error(`create project failed: ${res.status} ${await res.text()}`);
    }
    const project = (await res.json()) as TestProject;
    this.trackProject(project.id);
    return project;
  }

  async deleteProject(id: string) {
    const res = await this.authedFetch(`/api/projects/${id}`, { method: "DELETE" });
    if (!res.ok && res.status !== 404) {
      throw new Error(`delete project failed: ${res.status} ${await res.text()}`);
    }
    this.createdProjectIds = this.createdProjectIds.filter((projectId) => projectId !== id);
  }

  trackProject(id: string) {
    if (!this.createdProjectIds.includes(id)) {
      this.createdProjectIds.push(id);
    }
  }

  async dismissStarterContent(workspaceId?: string) {
    const res = await this.authedFetch("/api/me/starter-content/dismiss", {
      method: "POST",
      body: JSON.stringify({ workspace_id: workspaceId ?? this.workspaceId }),
    });
    if (!res.ok && res.status !== 409) {
      throw new Error(`dismiss starter content failed: ${res.status} ${await res.text()}`);
    }
  }

  async createIssue(title: string, opts?: Record<string, unknown>) {
    const res = await this.authedFetch("/api/issues", {
      method: "POST",
      body: JSON.stringify({ title, ...opts }),
    });
    const issue = await res.json();
    this.createdIssueIds.push(issue.id);
    return issue;
  }

  async deleteIssue(id: string) {
    await this.authedFetch(`/api/issues/${id}`, { method: "DELETE" });
  }


  /** Clean up all records created during this test. */
  async cleanup() {
    for (const id of [...this.createdProjectIds].reverse()) {
      try {
        await this.deleteProject(id);
      } catch {
        /* ignore — may already be deleted */
      }
    }
    this.createdProjectIds = [];

    for (const id of this.createdIssueIds) {
      try {
        await this.deleteIssue(id);
      } catch {
        /* ignore — may already be deleted */
      }
    }
    this.createdIssueIds = [];
  }

  getToken() {
    return this.token;
  }

  private async authedFetch(path: string, init?: RequestInit) {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((init?.headers as Record<string, string>) ?? {}),
    };
    if (this.token) headers["Authorization"] = `Bearer ${this.token}`;
    if (this.workspaceSlug) headers["X-Workspace-Slug"] = this.workspaceSlug;
    else if (this.workspaceId) headers["X-Workspace-ID"] = this.workspaceId;
    return fetch(`${API_BASE}${path}`, { ...init, headers });
  }
}
