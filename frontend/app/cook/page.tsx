export default function CookPage() {
  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h2 className="font-serif text-2xl font-semibold tracking-tight mb-6">
        Cook
      </h2>
      <div className="rounded-lg border border-border bg-card p-8 text-center">
        <p className="text-muted-foreground text-sm leading-relaxed max-w-md mx-auto">
          Describe what you feel like eating and the cook will propose a meal
          from your pantry.
        </p>
      </div>
    </div>
  );
}
