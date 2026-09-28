export default function PantryPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h2 className="font-serif text-2xl font-semibold tracking-tight mb-6">
        Pantry
      </h2>
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <p className="text-muted-foreground text-sm leading-relaxed max-w-md mx-auto">
          Your pantry is empty. Add what&apos;s in the fridge and cupboard — the
          cook uses what you actually have.
        </p>
      </div>
    </div>
  );
}
