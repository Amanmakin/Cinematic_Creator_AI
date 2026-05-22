/**
 * Diagnostic test — checks badge text after a real run.
 * Run once, then delete.
 */
import { test, expect } from "@playwright/test";

const PROMPT =
  "A modern, cinematic advertisement for a new kurti collection, " +
  "focusing on slow-motion movement and warm tones.";

test("diagnostic: badge text after run", async ({ page }) => {
  test.setTimeout(8 * 60 * 1000);

  // Capture all console messages from the page
  page.on("console", (msg) => console.log("PAGE LOG:", msg.type(), msg.text()));
  // Capture failed requests
  page.on("requestfailed", (req) =>
    console.log("REQUEST FAILED:", req.url(), req.failure()?.errorText),
  );
  // Capture all API responses
  page.on("response", async (res) => {
    if (res.url().includes("localhost:8000")) {
      console.log("API RESPONSE:", res.status(), res.url().replace("http://localhost:8000", ""));
    }
  });

  await page.goto("/");

  // Fill prompt first so button can become enabled
  await page.getByPlaceholder("Describe the cinematic scene…").fill(PROMPT);

  // Wait for project init
  await expect(page.getByRole("button", { name: "Generate" })).toBeEnabled({ timeout: 30_000 });
  await page.getByRole("button", { name: "Generate" }).click();

  // Wait for "Running…" to appear (confirms run started)
  await expect(page.getByRole("button", { name: "Running…" })).toBeVisible({ timeout: 15_000 });

  console.log("Run started — waiting for generate button to return to idle...");

  // Wait for run to finish (button changes back to "Generate")
  await expect(page.getByRole("button", { name: "Generate" })).toBeVisible({ timeout: 6 * 60 * 1000 });

  console.log("Run finished — checking badge element...");

  // Check what elements with data-testid exist
  const badgeCount = await page.locator("[data-testid='phase-status-badge']").count();
  console.log("Badge elements found:", badgeCount);

  if (badgeCount > 0) {
    const badgeText = await page.locator("[data-testid='phase-status-badge']").textContent();
    console.log("Badge text:", JSON.stringify(badgeText));
  }

  // Inspect the Zustand store state via page.evaluate
  const storeState = await page.evaluate(() => {
    // Try to read the store from the window if exposed
    const store = (window as any).__ZUSTAND_STORE__;
    if (store) return store.getState();

    // Fallback: find the store via React DevTools globals (not always available)
    return null;
  });
  if (storeState) {
    console.log("Store state:", JSON.stringify(storeState, null, 2).slice(0, 1000));
  }

  // Also dump all text content in the left panel
  const asideText = await page.locator("aside").innerText();
  console.log("Aside panel text (first 1000 chars):", asideText.slice(0, 1000));

  // Check if any approval buttons exist
  const approveCount = await page.locator("button:has-text('Approve')").count();
  const acceptCount = await page.locator("button:has-text('Accept')").count();
  console.log("Approve buttons:", approveCount, "Accept buttons:", acceptCount);

  // Look for any error text in the page
  const errorEls = await page.locator("text=/error|Error|failed|Failed/").allTextContents();
  console.log("Error elements:", errorEls.slice(0, 10));
});
