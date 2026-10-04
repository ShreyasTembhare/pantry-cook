import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8787";

type Item = { id: string; name: string; quantity: string };

async function abandonOpen(request: APIRequestContext) {
  const sessions = await request.get(`${API}/api/cook?status=awaiting_user`);
  expect(sessions.ok()).toBeTruthy();
  for (const session of (await sessions.json()) as { id: string }[]) {
    expect((await request.post(`${API}/api/cook/${session.id}/abandon`)).ok()).toBeTruthy();
  }
}

/** A leftover confirmation would block the next write, so answer it first. */
async function closeOpenConfirmation(request: APIRequestContext) {
  const response = await request.post(`${API}/api/chat/messages`, { data: { text: "no" } });
  expect(response.ok()).toBeTruthy();
}

async function items(request: APIRequestContext): Promise<Item[]> {
  const response = await request.get(`${API}/api/items`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as Item[];
}

async function deleteMatching(request: APIRequestContext, prefix: string) {
  for (const item of await items(request)) {
    if (item.name.startsWith(prefix)) {
      expect((await request.delete(`${API}/api/items/${item.id}`)).ok()).toBeTruthy();
    }
  }
}

async function say(page: Page, text: string) {
  const box = page.getByRole("textbox", { name: "Message Pip" });
  await expect(box).toBeEnabled();
  await box.fill(text);
  await box.press("Enter");
}

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

for (const [label, viewport] of [
  ["desktop", { width: 1280, height: 800 }],
  ["phone", { width: 390, height: 844 }],
] as const) {
  test.describe(`chat on ${label}`, () => {
    test.use({ viewport });

    test.beforeEach(async ({ request }) => {
      await closeOpenConfirmation(request);
      await abandonOpen(request);
      await deleteMatching(request, "Chat spec");
    });

    test.afterEach(async ({ request }) => {
      await abandonOpen(request);
      await deleteMatching(request, "Chat spec");
    });

    test("adds, confirms a removal, cooks, and keeps the pantry in step", async ({
      page,
      request,
    }) => {
      await page.goto("/");
      await expect(page.getByRole("textbox", { name: "Message Pip" })).toBeVisible();

      await say(page, "2 chat spec leeks and 500 g chat spec chicken");
      await expect(page.getByText("Added to the pantry.").last()).toBeVisible();
      let stock = await items(request);
      expect(stock.find((item) => item.name === "Chat spec leeks")).toBeTruthy();
      expect(Number(stock.find((item) => item.name === "Chat spec chicken")?.quantity)).toBe(500);

      await say(page, "remove the chat spec leeks");
      await expect(page.getByText("Remove Chat spec leeks?").first()).toBeVisible();
      await expect(page.getByRole("status", { name: "Conversation status" })).toContainText(
        "Waiting for you",
      );
      expect((await items(request)).some((item) => item.name === "Chat spec leeks")).toBeTruthy();

      await page.getByRole("button", { name: "Remove", exact: true }).click();
      await expect(page.getByText("Removed Chat spec leeks.").first()).toBeVisible();
      expect((await items(request)).some((item) => item.name === "Chat spec leeks")).toBeFalsy();

      await say(page, "something warm with the chat spec chicken");
      await expect(page.getByRole("status", { name: "Conversation status" })).toContainText(
        "Meal in progress",
      );
      await page.getByRole("button", { name: "Confirm", exact: true }).last().click();
      await expect(page.getByText("Final check. Confirming uses these ingredients.")).toBeVisible();
      await page.getByRole("button", { name: "Confirm", exact: true }).last().click();
      await expect(page.getByText(/^Cooked /).first()).toBeVisible();

      stock = await items(request);
      expect(Number(stock.find((item) => item.name === "Chat spec chicken")?.quantity)).toBeLessThan(500);
      await expect(page.getByRole("status", { name: "Conversation status" })).toBeHidden();
      await expectNoHorizontalOverflow(page);
    });

    test("keeps a failed message and lets the user retry it", async ({ page }) => {
      await page.goto("/");
      await expect(page.getByRole("textbox", { name: "Message Pip" })).toBeVisible();

      await page.route("**/api/chat/messages", (route) => route.abort("failed"));
      await say(page, "what's in the pantry");
      await expect(page.getByText("Not sent")).toBeVisible();
      await expect(page.locator('[data-slot="alert"]')).toContainText("Couldn't reach the kitchen");

      await page.unroute("**/api/chat/messages");
      await page.getByRole("button", { name: "Retry", exact: true }).click();
      await expect(page.getByText("Not sent")).toBeHidden();
      await expect(page.getByText("Here's what's on hand.").last()).toBeVisible();
      await expectNoHorizontalOverflow(page);
    });

    test("keeps the thread after a reload", async ({ page }) => {
      await page.goto("/");
      await say(page, "what did I cook");
      await expect(page.getByText("Meals you've cooked.").last()).toBeVisible();
      await page.reload();
      await expect(page.getByText("Meals you've cooked.").last()).toBeVisible();
    });
  });
}
