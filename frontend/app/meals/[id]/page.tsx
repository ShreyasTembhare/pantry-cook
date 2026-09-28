import { MealDetail } from "@/components/meals/meal-detail";

export const metadata = {
  title: "Meal · Pantry Cook",
};

export default async function MealPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <MealDetail id={id} />;
}
