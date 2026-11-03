import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  className?: string;
  variant?: "default" | "success" | "warning" | "danger" | "info" | "muted";
}

const variantClasses = {
  default: "bg-gray-800 text-gray-200",
  success: "bg-emerald-900/60 text-emerald-300",
  warning: "bg-amber-900/60 text-amber-300",
  danger: "bg-red-900/60 text-red-300",
  info: "bg-blue-900/60 text-blue-300",
  muted: "bg-gray-800/60 text-gray-500",
};

export function Badge({ children, className, variant = "default" }: BadgeProps) {
  return (
    <span className={cn(
      "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
      variantClasses[variant],
      className
    )}>
      {children}
    </span>
  );
}
