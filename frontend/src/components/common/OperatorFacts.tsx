import type { OperatorDisplay } from '@/lib/types'

/** Only API-owned scalar facts and evidence belong in readable operator cards. */
export function OperatorFacts({
  display,
  evidence = true,
}: {
  display?: OperatorDisplay
  evidence?: boolean
}) {
  return (
    <>
      {display?.fields.length ? (
        <dl className="operator-facts">
          {display.fields.map((field, index) => (
            <div key={`${field.label}-${index}`}>
              <dt>{field.label}</dt>
              <dd>{field.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}
      {evidence && display?.evidence.length ? (
        <ul className="operator-evidence">
          {display.evidence.map((fact, index) => (
            <li key={index}>{fact}</li>
          ))}
        </ul>
      ) : null}
    </>
  )
}
