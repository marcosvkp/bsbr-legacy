import type { HTMLAttributes } from "react";

type BadgeVariant = "default" | "accent" | "secondary" | "success" | "warning" | "danger";

const VARIANTS: Record<BadgeVariant, string> = {
  default: "bg-surface-2 text-muted",
  accent: "bg-accent/15 text-accent",
  secondary: "bg-secondary/15 text-secondary",
  success: "bg-success/15 text-success",
  warning: "bg-warning/15 text-warning",
  danger: "bg-danger/15 text-danger",
};

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export function Badge({
  variant = "default",
  className = "",
  ...props
}: BadgeProps) {
  const classes = [
    "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
    VARIANTS[variant],
    className,
  ].join(" ");
  return <span className={classes} {...props} />;
}
