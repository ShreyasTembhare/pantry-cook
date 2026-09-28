import { Button } from "@/components/ui/button";
import { cookErrorPresentation } from "@/lib/cook";

export function CookErrorCard({
  code,
  detail,
  pending = false,
  onRecover,
}: {
  code?: string;
  detail?: string;
  pending?: boolean;
  onRecover: () => void;
}) {
  const presentation = cookErrorPresentation(code, detail);

  return (
    <div role="alert" className="rounded-lg border border-destructive/40 px-4 py-4">
      <h3 className="font-serif text-xl leading-tight tracking-tight">The proposal stopped</h3>
      <p className="mt-2 max-w-prose text-sm leading-relaxed">{presentation.message}</p>
      <Button
        type="button"
        className="mt-4 h-11 lg:h-9"
        onClick={onRecover}
        disabled={pending}
      >
        {pending ? "Working" : presentation.action}
      </Button>
    </div>
  );
}
