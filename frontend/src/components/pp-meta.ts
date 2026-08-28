/** Metadados visuais dos 3 componentes de PP (cores dos tokens do tema). */
export const COMPONENT_META = {
  acc: {
    label: "Acc",
    text: "text-secondary",
    bar: "bg-secondary",
    dot: "bg-secondary",
    cell: "bg-secondary/10",
    border: "border-secondary/25",
  },
  tech: {
    label: "Tech",
    text: "text-accent",
    bar: "bg-accent",
    dot: "bg-accent",
    cell: "bg-accent/10",
    border: "border-accent/25",
  },
  speed: {
    label: "Speed",
    text: "text-success",
    bar: "bg-success",
    dot: "bg-success",
    cell: "bg-success/10",
    border: "border-success/25",
  },
} as const;

export type SubComponentKey = keyof typeof COMPONENT_META;
