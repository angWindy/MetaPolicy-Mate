"use client";

import type { ReactNode } from "react";

import { AppLayout, type AppLayoutProps } from "./AppLayout";
import { useCurrentUser } from "../../hooks/useCurrentUser";

export type AuthenticatedLayoutProps = Omit<
    AppLayoutProps,
    "user"
> & {
  children: ReactNode;
};

/**
 * Wrapper around `AppLayout` that injects the real JWT-derived user
 * (instead of a mock profile) into the sidebar/header.
 */
export function AuthenticatedLayout(
  props: AuthenticatedLayoutProps,
) {
  const currentUser = useCurrentUser();
  const { children, ...rest } = props;
  return (
    <AppLayout {...rest} user={currentUser}>
      {children}
    </AppLayout>
  );
}