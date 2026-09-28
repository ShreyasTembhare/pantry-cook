import { CookSessionView } from "@/components/cook/cook-session";

export const metadata = {
  title: "Proposal · Pantry Cook",
};

export default async function CookSessionPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CookSessionView id={id} />;
}
