import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import * as React from 'react'
import { cn } from '@/lib/utils'

const buttonVariants = cva(
  'inline-flex items-center justify-center gap-1.5 rounded-md text-sm font-medium transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-45 active:translate-y-px',
  {
    variants: {
      variant: {
        default:
          'border border-[var(--color-border)] bg-[var(--color-elevated)] text-[var(--color-fg)] hover:border-[var(--color-border-strong)] hover:bg-[var(--color-subtle)]',
        primary:
          'border border-[var(--color-accent)] bg-[var(--color-accent)] font-semibold text-white hover:bg-[var(--color-accent-hover)] hover:border-[var(--color-accent-hover)]',
        approve:
          'border border-[var(--color-success)] bg-[var(--color-success)] font-semibold text-white hover:brightness-105',
        danger:
          'border border-[var(--color-border)] bg-[var(--color-elevated)] text-[var(--color-danger)] hover:bg-[var(--color-danger-soft)] hover:border-[var(--color-danger)]',
        ghost: 'border border-transparent bg-transparent hover:bg-[var(--color-subtle)]',
      },
      size: {
        default: 'h-9 px-3 py-1.5',
        sm: 'h-8 px-2.5 text-xs',
        lg: 'h-10 px-4',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
  },
)
Button.displayName = 'Button'
