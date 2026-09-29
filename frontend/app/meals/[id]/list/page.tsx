import { ShoppingList } from "@/components/meals/shopping-list";

export const metadata = {
  title: "Shopping list · Pantry Cook",
};

export default async function ShoppingListPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ShoppingList id={id} />;
}
