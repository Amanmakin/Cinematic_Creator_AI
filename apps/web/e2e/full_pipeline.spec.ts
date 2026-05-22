/**
 * Full pipeline E2E test — CinematicVideoCreator
 *
 * Initial prompt: "A modern, cinematic advertisement for a new kurti collection,
 * focusing on slow-motion movement and warm tones."
 *
 * The test drives the browser through every approval gate the pipeline surfaces:
 *   previsualization_generated → Approve (wireframe)
 *   model_generated            → Approve (2D/2.5D renders)
 *   awaiting_human_approval    → Accept  (high-ambiguity fallback)
 *   speculative_batching       → Variant A (medium-ambiguity fallback)
 *
 * It then asserts the pipeline reaches "completed" or "render_completed"
 * with a valid scene graph, satisfying all plan phases (Plans 1–9).
 *
 * Prerequisites (must be running before `npm run test:e2e`):
 *   API:  cd apps/api && uv run uvicorn api.main:app --reload
 *   Web:  cd apps/web && npm run dev   (playwright starts it automatically)
 */

import { test, expect, type Page } from "@playwright/test";

// ── Constants ────────────────────────────────────────────────────────────────

const INITIAL_PROMPT =
  "A modern, cinematic advertisement for a new kurti collection, " +
  "focusing on slow-motion movement and warm tones.";

const TERMINAL_STATUSES = [
  "completed",
  "render_completed",
  "failed",
  "physical_validation_failed",
  "dsl_validation_failed",
  "dsl_validation_error",
  "budget_exceeded",
  "render_timed_out",
] as const;

const APPROVAL_GATES = [
  "awaiting_human_approval",
  "speculative_batching",
  "previsualization_generated",
  "model_generated",
] as const;

type TerminalStatus = (typeof TERMINAL_STATUSES)[number];
type ApprovalGate = (typeof APPROVAL_GATES)[number];

const SUCCESS_STATUSES: TerminalStatus[] = ["completed", "render_completed"];
const ALL_INTERESTING = [...TERMINAL_STATUSES, ...APPROVAL_GATES] as string[];

// ── Helpers ──────────────────────────────────────────────────────────────────

/**
 * Block until the phase-status badge shows one of the interesting statuses
 * (a gate that needs human action OR a terminal state).
 *
 * Uses waitForFunction so Playwright polls the live DOM instead of relying
 * on network-level SSE observation.
 */
async function waitForInterestingStatus(
  page: Page,
  timeoutMs = 6 * 60 * 1000,
): Promise<string> {
  await page.waitForFunction(
    (statuses: string[]) => {
      const badge = document.querySelector("[data-testid='phase-status-badge']");
      if (!badge) return false;
      return statuses.includes((badge.textContent ?? "").trim());
    },
    ALL_INTERESTING,
    { timeout: timeoutMs },
  );

  const text = await page.getByTestId("phase-status-badge").textContent();
  return (text ?? "").trim();
}

/**
 * After clicking an approval button the badge will briefly stay on the gate
 * status while the SSE stream is starting.  Wait until it moves off.
 */
async function waitForStatusToLeave(
  page: Page,
  fromStatus: string,
  timeoutMs = 30_000,
): Promise<void> {
  await page.waitForFunction(
    ({ from }: { from: string }) => {
      const badge = document.querySelector("[data-testid='phase-status-badge']");
      if (!badge) return false;
      return (badge.textContent ?? "").trim() !== from;
    },
    { from: fromStatus },
    { timeout: timeoutMs },
  );
}

/**
 * Dispatch the right UI action for each approval gate.
 *
 * previsualization_generated  → click "Approve" in the bottom-bar wireframe panel
 * model_generated             → click "Approve" in the bottom-bar model panel
 * awaiting_human_approval     → click "Accept" in the centered modal
 * speculative_batching        → click "Variant A" card in the centered modal
 */
async function handleApprovalGate(page: Page, status: ApprovalGate): Promise<void> {
  switch (status) {
    case "previsualization_generated": {
      const btn = page.getByRole("button", { name: "Approve" });
      await expect(btn).toBeEnabled({ timeout: 15_000 });
      await btn.click();
      break;
    }

    case "model_generated": {
      const btn = page.getByRole("button", { name: "Approve" });
      await expect(btn).toBeEnabled({ timeout: 15_000 });
      await btn.click();
      break;
    }

    case "awaiting_human_approval": {
      // Modal: "Accept" button (no custom prompt, accept as-is)
      const btn = page.getByRole("button", { name: "Accept" });
      await expect(btn).toBeEnabled({ timeout: 15_000 });
      await btn.click();
      break;
    }

    case "speculative_batching": {
      // Pick the first generated variant
      const btn = page.locator("button", { hasText: "Variant A" });
      await expect(btn).toBeEnabled({ timeout: 15_000 });
      await btn.click();
      break;
    }
  }
}

// ── Tests ────────────────────────────────────────────────────────────────────

test.describe("CinematicVideoCreator — Full Pipeline (Plans 1–9)", () => {
  // Each test may call real OpenAI + Blender + image-gen — allow up to 10 min
  test.setTimeout(10 * 60 * 1000);

  // ── Phase 1: Submit the initial kurti prompt ────────────────────────────

  test("app loads and project initialises before the first run", async ({ page }) => {
    await page.goto("/");

    // The prompt textarea must be present and editable immediately
    const textarea = page.getByPlaceholder("Describe the cinematic scene…");
    await expect(textarea).toBeVisible({ timeout: 15_000 });
    await expect(textarea).toBeEditable();

    // Fill the prompt — the Generate button is also gated on !prompt.trim(),
    // so we must type before waiting for it to become enabled.
    await textarea.fill(INITIAL_PROMPT);

    // Once initProject() resolves (project_id stored in Zustand) the button
    // transitions from disabled → enabled.
    await expect(page.getByRole("button", { name: "Generate" })).toBeEnabled({
      timeout: 30_000,
    });
  });

  // ── Phase 2: Full end-to-end pipeline with all approval gates ──────────

  test("kurti prompt drives the full pipeline to completed", async ({ page }) => {
    await page.goto("/");

    // ── Step 1: Fill prompt first (button disabled until prompt + projectId) ─
    await page.getByPlaceholder("Describe the cinematic scene…").fill(INITIAL_PROMPT);

    // ── Step 2: Wait for project init (initProject must resolve) ─────────
    const generateBtn = page.getByRole("button", { name: "Generate" });
    await expect(generateBtn).toBeEnabled({ timeout: 30_000 });

    // Verify textarea content before submitting
    await expect(page.getByPlaceholder("Describe the cinematic scene…")).toHaveValue(
      INITIAL_PROMPT,
    );

    // ── Step 3: Submit and confirm the run starts ─────────────────────────
    await generateBtn.click();

    // The button text flips to "Running…" once isRunning:true
    await expect(page.getByRole("button", { name: "Running…" })).toBeVisible({
      timeout: 15_000,
    });

    // ── Step 4: Drive the pipeline through all gates ──────────────────────
    let finalStatus = "";
    const MAX_GATE_ITERATIONS = 10; // safety cap; normal run hits 2 gates max

    for (let i = 0; i < MAX_GATE_ITERATIONS; i++) {
      const status = await waitForInterestingStatus(page);

      // Terminal state reached — we're done
      if ((TERMINAL_STATUSES as readonly string[]).includes(status)) {
        finalStatus = status;
        break;
      }

      // Approval gate — handle it and wait for the badge to advance
      const gate = status as ApprovalGate;
      await handleApprovalGate(page, gate);

      // Give the SSE stream a moment to start so the badge moves off the gate
      await waitForStatusToLeave(page, gate, 30_000);
    }

    // ── Step 5: Assert success ────────────────────────────────────────────
    expect(SUCCESS_STATUSES, `Pipeline ended with unexpected status: "${finalStatus}"`).toContain(
      finalStatus as TerminalStatus,
    );

    // The phase-status badge should display the final status
    await expect(page.getByTestId("phase-status-badge")).toHaveText(finalStatus);
  });

  // ── Phase 3: Assert scene quality after completion ──────────────────────

  test("completed run has a valid scene graph in the viewport", async ({ page }) => {
    // Re-run the full pipeline (isolated project per test)
    await page.goto("/");

    await page.getByPlaceholder("Describe the cinematic scene…").fill(INITIAL_PROMPT);
    const generateBtn = page.getByRole("button", { name: "Generate" });
    await expect(generateBtn).toBeEnabled({ timeout: 30_000 });
    await generateBtn.click();
    await expect(page.getByRole("button", { name: "Running…" })).toBeVisible({ timeout: 15_000 });

    // Drive through all gates
    let finalStatus = "";
    for (let i = 0; i < 10; i++) {
      const status = await waitForInterestingStatus(page);
      if ((TERMINAL_STATUSES as readonly string[]).includes(status)) {
        finalStatus = status;
        break;
      }
      await handleApprovalGate(page, status as ApprovalGate);
      await waitForStatusToLeave(page, status, 30_000);
    }

    expect(SUCCESS_STATUSES).toContain(finalStatus);

    // After gltf_assembled the Viewport loads a Three.js canvas
    const canvas = page.locator("canvas");
    await expect(canvas).toBeVisible({ timeout: 30_000 });

    // The timeline should contain at least the key pipeline stages
    const phaseLabel = page.locator(".text-xs.font-semibold.tracking-wide.uppercase");
    await expect(phaseLabel).toBeVisible();
  });

  // ── Phase 4: Wireframe approval gate ───────────────────────────────────

  test("wireframe approval bottom bar appears and can be approved", async ({ page }) => {
    await page.goto("/");
    await page.getByPlaceholder("Describe the cinematic scene…").fill(INITIAL_PROMPT);
    await expect(page.getByRole("button", { name: "Generate" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Generate" }).click();
    await expect(page.getByRole("button", { name: "Running…" })).toBeVisible({ timeout: 15_000 });

    // Wait specifically for the wireframe gate
    let hitWireframeGate = false;
    for (let i = 0; i < 10; i++) {
      const status = await waitForInterestingStatus(page);

      if ((TERMINAL_STATUSES as readonly string[]).includes(status)) break;

      if (status === "previsualization_generated") {
        hitWireframeGate = true;

        // The bottom approval bar must be visible
        const bottomBar = page.locator("text=Wireframe Previsualization");
        await expect(bottomBar).toBeVisible({ timeout: 10_000 });

        // Both Feedback and Approve buttons should be present
        await expect(page.getByRole("button", { name: "Feedback" })).toBeVisible();
        await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
        await expect(page.getByRole("button", { name: "Approve" })).toBeEnabled();

        // Approve and continue
        await page.getByRole("button", { name: "Approve" }).click();
        await waitForStatusToLeave(page, status, 30_000);
      } else {
        await handleApprovalGate(page, status as ApprovalGate);
        await waitForStatusToLeave(page, status, 30_000);
      }
    }

    expect(hitWireframeGate, "Pipeline never reached previsualization_generated").toBe(true);
  });

  // ── Phase 5: Model approval gate ───────────────────────────────────────

  test("model approval bottom bar appears and can be approved", async ({ page }) => {
    await page.goto("/");
    await page.getByPlaceholder("Describe the cinematic scene…").fill(INITIAL_PROMPT);
    await expect(page.getByRole("button", { name: "Generate" })).toBeEnabled({ timeout: 30_000 });
    await page.getByRole("button", { name: "Generate" }).click();
    await expect(page.getByRole("button", { name: "Running…" })).toBeVisible({ timeout: 15_000 });

    let hitModelGate = false;
    for (let i = 0; i < 10; i++) {
      const status = await waitForInterestingStatus(page);

      if ((TERMINAL_STATUSES as readonly string[]).includes(status)) break;

      if (status === "model_generated") {
        hitModelGate = true;

        // The bottom bar should show model renders header
        const header = page.locator("text=Model Renders");
        await expect(header).toBeVisible({ timeout: 10_000 });

        // Approve and continue
        await expect(page.getByRole("button", { name: "Approve" })).toBeEnabled({ timeout: 15_000 });
        await page.getByRole("button", { name: "Approve" }).click();
        await waitForStatusToLeave(page, status, 30_000);
      } else {
        await handleApprovalGate(page, status as ApprovalGate);
        await waitForStatusToLeave(page, status, 30_000);
      }
    }

    expect(hitModelGate, "Pipeline never reached model_generated").toBe(true);
  });
});
