import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 rounded-md text-sm font-medium cursor-pointer transition-colors duration-150 disabled:opacity-45 active:brightness-95',
  {
    variants: {
      variant: {
        default:
          'border border-[var(--color-border)] bg-[var(--color-elevated)] text-[var(--color-fg)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-subtle)]',
        primary:
          'border border-[var(--color-accent)] bg-[var(--color-accent)] font-semibold text-[var(--color-on-accent)] hover:bg-[var(--color-accent-hover)] hover:border-[var(--color-accent-hover)]',
        approve:
          'border border-[var(--color-success)] bg-[var(--color-success)] font-semibold text-[var(--color-on-success)] hover:brightness-105',
        danger:
          'border border-[var(--color-border)] bg-[var(--color-elevated)] text-[var(--color-danger)] hover:bg-[var(--color-danger-soft)] hover:border-[var(--color-danger)]',
        ghost: 'border border-transparent bg-transparent hover:bg-[var(--color-subtle)]',
      },
      size: {
        default: 'min-h-10 px-3.5 py-2 max-md:min-h-11',
        sm: 'min-h-9 px-3 text-xs max-md:min-h-11',
        lg: 'min-h-11 px-5',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    )
  },
)
Button.displayName = 'Button'
