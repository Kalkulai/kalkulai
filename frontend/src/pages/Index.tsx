import { lazy, Suspense } from "react";

const KalkulaiInterface = lazy(() => import("@/components/KalkulaiInterface"));

const Index = () => {
  return (
    <Suspense
      fallback={
        <div className="flex h-full items-center justify-center text-muted-foreground">
          Interface wird geladen …
        </div>
      }
    >
      <KalkulaiInterface />
    </Suspense>
  );
};

export default Index;
