import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const API = "http://127.0.0.1:8787";

test.use({ viewport: { width: 390, height: 844 } });

function isoIn(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() + days);
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

async function abandonOpen(request: APIRequestContext) {
  const sessions = await request.get(`${API}/api/cook?status=awaiting_user`);
  expect(sessions.ok()).toBeTruthy();
  for (const session of (await sessions.json()) as { id: string }[]) {
    expect((await request.post(`${API}/api/cook/${session.id}/abandon`)).ok()).toBeTruthy();
  }
}

async function deleteNamed(request: APIRequestContext, name: string) {
  const items = await request.get(`${API}/api/items`);
  expect(items.ok()).toBeTruthy();
  for (const item of (await items.json()) as { id: string; name: string }[]) {
    if (item.name === name) {
      expect((await request.delete(`${API}/api/items/${item.id}`)).ok()).toBeTruthy();
    }
  }
}

async function addItem(page: Page, name: string, quantity: string, unit: string, expiry = "") {
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Quantity").fill(quantity);
  if (unit !== "g") {
    await page.getByLabel("Unit").click();
    await page.getByRole("option", { name: unit, exact: true }).click();
  }
  if (expiry) await page.getByLabel("Expiry").fill(expiry);
  await page.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText(`Added ${name}`)).toBeVisible();
}

test("cooks from the phone: add, propose, revise, confirm", async ({ page, request }) => {
  await abandonOpen(request);
  await deleteNamed(request, "Spec Leeks");
  await deleteNamed(request, "Spec Eggs");

  await page.goto("/pantry");
  await expect(page.getByRole("navigation", { name: "Mobile" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden();
  await expect(page.getByRole("heading", { name: "Pantry", exact: true })).toBeVisible();

  await addItem(page, "Spec Leeks", "300", "g", isoIn(2));
  await addItem(page, "Spec Eggs", "6", "count");
  await expect(page.getByRole("button", { name: /^Spec Leeks/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /^Spec Eggs/ })).toBeVisible();

  await page.getByRole("navigation", { name: "Mobile" }).getByRole("link", { name: "Cook" }).click();
  await page
    .getByLabel("What do you want to cook?")
    .fill("something quick with the spec leeks and spec eggs");
  await page.getByRole("button", { name: "Propose" }).click();

  await expect(page.getByRole("button", { name: "Confirm" })).toBeVisible();
  await page.getByRole("button", { name: "Revise" }).click();
  await page.getByRole("textbox", { name: "Revision note" }).fill("fewer steps");
  await page.getByRole("button", { name: "Send revision" }).click();
  await expect(page.getByText("Attempt 2").first()).toBeVisible();

  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Cooked. Pantry updated.")).toBeVisible();

  const items = (await (await request.get(`${API}/api/items`)).json()) as {
    name: string;
    quantity: string;
  }[];
  expect(Number(items.find((item) => item.name === "Spec Leeks")?.quantity)).toBe(150);
  expect(Number(items.find((item) => item.name === "Spec Eggs")?.quantity)).toBe(3);
});
