import { OperatorFacts } from '@/components/common/OperatorFacts'
import type { RunDetail } from '@/types/api'

/** Final report: verified facts only; the model's own words stay in the engineering record. */
export function IncidentReport({ run }: { run: RunDetail }) {
  const report = run.operator?.report || run.result?.operator
  return (
    <section className="mb-5 border-b border-[var(--color-border)] pb-5">
      <h2 className="section-eyebrow mb-3">Incident report</h2>
      <div className="activity-outcome">
        <p className="m-0 text-sm font-semibold">{report?.title || 'Investigation finished'}</p>
        <p className="mt-1 text-[13px] leading-relaxed">
          {report?.summary || 'Review the recorded outcome in the engineering record.'}
        </p>
      </div>
      <OperatorFacts display={report || undefined} />
    </section>
  )
}
