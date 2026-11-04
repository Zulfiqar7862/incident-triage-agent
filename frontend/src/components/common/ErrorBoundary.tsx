import { Component, type ErrorInfo, type ReactNode } from 'react'
import { ErrorBanner } from '@/components/common/ErrorBanner'
import { mapError } from '@/lib/errors'

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
      const friendly = mapError(this.state.error)
      if (this.props.fallbackTitle) friendly.title = this.props.fallbackTitle
      return (
        <ErrorBanner
          className="m-4"
          error={friendly}
          onAction={() => this.setState({ error: null })}
        />
      )
    }
    return this.props.children
  }
}
