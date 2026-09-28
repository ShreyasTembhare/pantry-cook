import { expect, test, type APIRequestContext } from "@playwright/test";

const API = "http://127.0.0.1:8787";

async function abandonOpen(request: APIRequestContext) {
  const sessions = await request.get(`${API}/api/cook?status=awaiting_user`);
  expect(sessions.ok()).toBeTruthy();
  for (const session of (await sessions.json()) as { id: string }[]) {
    const abandoned = await request.post(`${API}/api/cook/${session.id}/abandon`);
    expect(abandoned.ok()).toBeTruthy();
  }
}

async function deleteNamed(request: APIRequestContext, name: string) {
  const items = await request.get(`${API}/api/items`);
  expect(items.ok()).toBeTruthy();
  for (const item of (await items.json()) as { id: string; name: string }[]) {
    if (item.name !== name) continue;
    const removed = await request.delete(`${API}/api/items/${item.id}`);
    expect(removed.ok()).toBeTruthy();
  }
}

test("reloads an awaiting proposal from the checkpoint and still cooks it", async ({
  page,
  request,
}) => {
  await abandonOpen(request);
  await deleteNamed(request, "Persist Fennel");
  const created = await request.post(`${API}/api/items`, {
    data: { name: "Persist Fennel", quantity: "300", unit: "g", expires_on: "2026-12-01" },
  });
  expect(created.ok()).toBeTruthy();

  await page.goto("/cook");
  await page.getByLabel("What do you want to cook?").fill("something warm with the persist fennel");
  await page.getByRole("button", { name: "Propose" }).click();
  await expect(page.getByRole("button", { name: "Confirm" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /Fennel/ })).toBeVisible();

  await page.reload();
  await expect(page.getByRole("heading", { name: /Fennel/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Confirm" })).toBeVisible();
  await expect(page.getByText("150 g of 300 g").first()).toBeVisible();

  await page.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText("Cooked. Pantry updated.")).toBeVisible();

  const items = (await (await request.get(`${API}/api/items`)).json()) as {
    name: string;
    quantity: string;
  }[];
  const fennel = items.find((item) => item.name === "Persist Fennel");
  expect(Number(fennel?.quantity)).toBe(150);
});
