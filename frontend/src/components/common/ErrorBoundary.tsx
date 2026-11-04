import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button } from '@/components/ui/button'

type Props = { children: ReactNode; fallbackTitle?: string }
type State = { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error boundary', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="m-4 rounded-lg border border-[var(--color-danger)] bg-[var(--color-danger-soft)] p-4 text-[var(--color-danger)]" role="alert">
          <div className="font-semibold">{this.props.fallbackTitle || 'Something went wrong in the operator console'}</div>
          <p className="mt-1 text-sm opacity-90">{this.state.error.message}</p>
          <Button className="mt-3" onClick={() => this.setState({ error: null })}>
            Try again
          </Button>
        </div>
      )
    }
    return this.props.children
  }
}
