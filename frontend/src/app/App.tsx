import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom'
import { Toaster } from 'sonner'
import { ErrorBoundary } from '@/components/common/ErrorBoundary'
import { ConsolePage } from '@/pages/ConsolePage'

const qc = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 2_000, retry: 1 },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <ErrorBoundary>
        <HashRouter>
          <Routes>
            <Route path="/" element={<ConsolePage />} />
            <Route path="/runs/:runId" element={<ConsolePage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </HashRouter>
        <Toaster richColors position="bottom-right" closeButton />
      </ErrorBoundary>
    </QueryClientProvider>
  )
}
