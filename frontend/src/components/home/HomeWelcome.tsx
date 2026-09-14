"use client";

import { useCurrentUser } from "@/hooks/useCurrentUser";
import { HomeDashboard } from "./HomeDashboard";

export function HomeWelcome() {
  const user = useCurrentUser();
  return <HomeDashboard userName={user.name || "bạn"} />;
}
