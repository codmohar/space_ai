import { expect, test } from "@playwright/test";

test.describe("MISSIONWISE AI — Full End-to-End Demo Flow", () => {
  test("Demo Mode walkthrough: STAIR RAG -> PDF viewer -> Similar -> Failure Chain -> KG -> Voice -> Eval -> Admin", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    const pageErrors: string[] = [];

    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      pageErrors.push(err.message);
    });

    await page.goto("/");

    // 1. Verify safety disclaimer and console shell
    await expect(
      page.getByText(
        "MISSIONWISE is a knowledge-support tool, not a certifier of spacecraft safety."
      )
    ).toBeVisible();

    // 2. Toggle Demo Mode & inspect walkthrough bar
    await page.getByTestId("toggle-demo-mode").click();
    const demoBar = page.getByTestId("demo-walkthrough-bar");
    await expect(demoBar).toBeVisible();

    // 3. Step 01: Execute thermal & oxygen tank STAIR RAG query (served from verified demo cache or live pipeline)
    await page.getByTestId("demo-execute-step").click();

    // Verify cited answer + STAIR confidence UI + Citation PDF viewer
    await expect(page.getByText(/Confidence:/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(/NASA-A13-1970/i).first()).toBeVisible({ timeout: 30_000 });

    // Verify Voice Console bar is mounted on Research Assistant
    await expect(page.getByText(/Hold to Talk|Hands-Free/i).first()).toBeVisible();

    // 4. Step 03: Similar Past Failures Search
    await demoBar.getByRole("button", { name: "03" }).click();
    await page.getByTestId("demo-execute-step").click();
    await expect(page.getByText(/Similar Past Failures/i).first()).toBeVisible();
    await expect(page.getByText(/Reconstruct Chain/i).first()).toBeVisible({ timeout: 25_000 });

    // 5. Step 04: Failure Chain Analyzer
    await demoBar.getByRole("button", { name: "04" }).click();
    await page.getByTestId("demo-execute-step").click();
    await expect(page.getByText(/Failure Chain Analyzer/i).first()).toBeVisible();

    const rfNode = page.locator(".react-flow__node").first();
    const hasNodes = await rfNode.isVisible().catch(() => false);
    if (!hasNodes) {
      await page.getByRole("button", { name: /Reconstruct Failure Chain/i }).click();
    }
    await expect(rfNode).toBeVisible({ timeout: 45_000 });
    await rfNode.click();
    const openPdfBtn = page.getByRole("button", { name: /Open PDF at Page/i });
    await expect(openPdfBtn).toBeVisible();
    await openPdfBtn.click();
    await expect(page.getByText(/Source & Licence|Public Domain/i).first()).toBeVisible({
      timeout: 15_000,
    });

    // Follow-up question on the failure chain inspector (text/voice shared backend)
    const followInput = page.getByPlaceholder(/Ask a follow-up/i);
    if (await followInput.isVisible().catch(() => false)) {
      await followInput.fill("What was the initial issue?");
      await page.getByRole("button", { name: /^Ask$/i }).click();
      await expect(page.getByText(/Confidence:/i).first()).toBeVisible({ timeout: 30_000 });
    }

    // 6. Step 05: Engineering Knowledge Graph multi-hop query
    await demoBar.getByRole("button", { name: "05" }).click();
    await page.getByTestId("demo-execute-step").click();
    await expect(page.getByText(/Engineering Knowledge Graph/i).first()).toBeVisible();
    await expect(page.locator(".react-flow__node").first()).toBeVisible({ timeout: 20_000 });

    // 7. Navigate to Evaluation page & verify real measured /scripts benchmarks
    await page.getByRole("button", { name: /Evaluation/i }).click();
    await expect(page.getByText(/BM25/i).first()).toBeVisible();
    await expect(page.getByText(/Not yet evaluated/i)).toHaveCount(0);

    // 8. Navigate to Admin & Audit page, sign in via JWT, inspect RBAC + telemetry logs
    await page.getByRole("button", { name: /Admin & Audit/i }).click();
    await page.getByRole("button", { name: /Sign In \(JWT\)/i }).click();
    await expect(page.getByText(/Role-Based Access Control/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText(/Retrieval & Model\/Prompt Version Logs/i)).toBeVisible();
    await expect(page.getByText(/Security Audit Logs/i)).toBeVisible();

    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
