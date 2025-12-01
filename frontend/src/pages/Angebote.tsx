import { lazy, Suspense } from "react";

const KalkulaiInterface = lazy(() => import("@/components/KalkulaiInterface"));

// Wrapper-Komponente die das bestehende Interface einbettet
// ohne den alten Header (da jetzt im MainLayout)
export default function Angebote() {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center text-muted-foreground min-h-[400px]">
          <div className="text-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary mx-auto mb-4"></div>
            <p>Interface wird geladen …</p>
          </div>
        </div>
      }
    >
      <KalkulaiInterface embedded />
    </Suspense>
  );
}

