export default function MealsPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h2 className="font-serif text-2xl font-semibold tracking-tight mb-6">
        Meals
      </h2>
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <p className="text-muted-foreground text-sm leading-relaxed max-w-md mx-auto">
          No meals yet. Cook something.
        </p>
      </div>
    </div>
  );
}
