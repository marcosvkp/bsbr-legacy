import type { HTMLAttributes } from "react";

export function Card({ className = "", ...props }: HTMLAttributes<HTMLDivElement>) {
  const classes = [
    "rounded-lg border border-border-subtle bg-surface shadow-sm",
    className,
  ].join(" ");
  return <div className={classes} {...props} />;
}

export function CardHeader({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  const classes = ["flex flex-col gap-1 p-4 pb-2", className].join(" ");
  return <div className={classes} {...props} />;
}

export function CardTitle({
  className = "",
  ...props
}: HTMLAttributes<HTMLHeadingElement>) {
  const classes = ["text-base font-semibold tracking-tight", className].join(
    " ",
  );
  return <h3 className={classes} {...props} />;
}

export function CardDescription({
  className = "",
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  const classes = ["text-sm text-muted", className].join(" ");
  return <p className={classes} {...props} />;
}

export function CardContent({
  className = "",
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  const classes = ["p-4 pt-2", className].join(" ");
  return <div className={classes} {...props} />;
}
