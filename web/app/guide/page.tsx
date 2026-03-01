"use client";

import { useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";

/**
 * Legacy guide page — redirects to the new /results page.
 * Kept for backward compatibility with existing links/bookmarks.
 */
function GuideRedirect() {
  const searchParams = useSearchParams();

  useEffect(() => {
    // Forward all query params to the new results page
    const params = new URLSearchParams();
    searchParams.forEach((value, key) => {
      params.set(key, value);
    });
    window.location.href = `/results?${params.toString()}`;
  }, [searchParams]);

  return (
    <div className="flex min-h-screen items-center justify-center">
      <p className="text-muted">Redirecting to your guide...</p>
    </div>
  );
}

export default function GuidePage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center">
          <p className="text-muted">Loading...</p>
        </div>
      }
    >
      <GuideRedirect />
    </Suspense>
  );
}
