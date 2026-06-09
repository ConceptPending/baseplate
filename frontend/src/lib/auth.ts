"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { checkAuth } from "./api";

export function useRequireAuth() {
  const [isAuth, setIsAuth] = useState<boolean | null>(null);
  const router = useRouter();
  const pathname = usePathname();

  // Re-validate whenever the admin route changes. The admin layout doesn't
  // remount on client navigation, so without the pathname dependency the check
  // never re-runs after login — leaving the dashboard stuck on "Loading" until
  // a manual refresh.
  useEffect(() => {
    let active = true;
    checkAuth()
      .then(() => active && setIsAuth(true))
      .catch(() => {
        if (!active) return;
        setIsAuth(false);
        router.push("/admin/login");
      });
    return () => {
      active = false;
    };
  }, [pathname, router]);

  return isAuth;
}
