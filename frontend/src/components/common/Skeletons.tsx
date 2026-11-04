export function RunListSkeleton() {
  return (
    <ul className="space-y-2" aria-hidden>
      {[0, 1, 2].map((i) => (
        <li key={i} className="animate-shimmer h-14 rounded-lg" />
      ))}
    </ul>
  )
}

export function RunViewSkeleton() {
  return (
    <div className="space-y-4 p-6" aria-busy>
      <div className="animate-shimmer h-8 w-2/3 rounded-md" />
      <div className="animate-shimmer h-4 w-full rounded-md" />
      <div className="animate-shimmer h-24 w-full rounded-lg" />
      <div className="animate-shimmer h-24 w-full rounded-lg" />
    </div>
  )
}
