import { useEffect, useMemo, useRef, useState } from 'react'

const WORD_NUMBERS = ['zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight']

function words(n) {
  const w = n >= 0 && n < WORD_NUMBERS.length ? WORD_NUMBERS[n] : String(n)
  return w.charAt(0).toUpperCase() + w.slice(1)
}

function initialResponses(guests, existingRsvps) {
  const responses = {}
  const rsvpsByGuestId = new Map(existingRsvps.map((r) => [r.guest_id, r]))
  for (const g of guests) {
    const r = rsvpsByGuestId.get(g.id)
    responses[g.id] = {
      attending: r ? r.attending : null,
      meal_choice: r ? r.meal_choice : '',
      plus_one_attending: r ? r.plus_one_attending : false,
      plus_one_name: r ? r.plus_one_name : '',
      plus_one_meal: r ? r.plus_one_meal : '',
      notes: r ? r.notes : '',
    }
  }
  return responses
}

export default function RsvpForm(props) {
  const {
    csrfToken,
    submitUrl,
    party,
    guests = [],
    existingRsvps = [],
    mealChoices = [],
    replyByDate,
  } = props

  const hasFullReceipt = useMemo(
    () => guests.length > 0 && guests.every((g) => existingRsvps.some((r) => r.guest_id === g.id)),
    [guests, existingRsvps],
  )

  const [mode, setMode] = useState(hasFullReceipt ? 'receipt' : 'form')
  const [receipt, setReceipt] = useState(hasFullReceipt ? existingRsvps : null)
  const [responses, setResponses] = useState(() => initialResponses(guests, existingRsvps))
  const [errors, setErrors] = useState([])
  const [serverError, setServerError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const errorSummaryRef = useRef(null)

  useEffect(() => {
    if (errors.length > 0 && errorSummaryRef.current) {
      errorSummaryRef.current.focus()
      errorSummaryRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, [errors])

  const updateResponse = (guestId, field, value) => {
    setResponses((prev) => ({ ...prev, [guestId]: { ...prev[guestId], [field]: value } }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (submitting) return
    setSubmitting(true)
    setServerError('')

    const body = {
      guests: guests.map((g) => ({
        guest_id: g.id,
        attending: responses[g.id].attending === true,
        meal_choice: responses[g.id].meal_choice,
        plus_one_attending: responses[g.id].plus_one_attending,
        plus_one_name: responses[g.id].plus_one_name,
        plus_one_meal: responses[g.id].plus_one_meal,
        notes: responses[g.id].notes,
      })),
    }

    try {
      const res = await fetch(submitUrl, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrfToken,
        },
        body: JSON.stringify(body),
      })
      const data = await res.json().catch(() => ({ ok: false, errors: [{ message: 'Malformed response.' }] }))
      if (res.ok && data.ok) {
        setReceipt(data.receipt || [])
        setErrors([])
        setMode('receipt')
        window.scrollTo({ top: 0, behavior: 'smooth' })
      } else {
        setErrors(data.errors || [{ message: 'Something went wrong.' }])
      }
    } catch (err) {
      setServerError("Couldn't reach the server. Try again in a moment.")
    } finally {
      setSubmitting(false)
    }
  }

  if (mode === 'receipt' && receipt) {
    return (
      <Receipt
        receipt={receipt}
        onEdit={() => {
          setMode('form')
          setResponses(initialResponses(guests, receipt))
        }}
      />
    )
  }

  return (
    <form className="rsvp-form" onSubmit={handleSubmit} noValidate>
      <div className="rsvp-form__intro">
        <div className="rsvp-form__step-marker">
          <span className="rsvp-form__step-marker-tag">Step 2 of 2</span>
          <span className="rsvp-form__step-marker-rule" aria-hidden="true"></span>
          <span>
            code {party.lookupCode} · <a href="/rsvp/">not you?</a>
          </span>
        </div>
        <p className="rsvp-form__lede">
          Please reply by <strong>{replyByDate}</strong>.
        </p>
      </div>

      {errors.length > 0 && (
        <div
          ref={errorSummaryRef}
          tabIndex={-1}
          role="alert"
          className="form-error-summary"
          aria-live="assertive"
        >
          <div className="form-error-summary__title">
            {errors.length === 1
              ? 'One thing needs your attention'
              : `${words(errors.length)} things need your attention`}
          </div>
          <ul>
            {errors.map((err, i) => {
              const anchor = err.guest_id
                ? `#guest-${err.guest_id}-${err.field || 'top'}`
                : undefined
              return (
                <li key={i}>
                  {anchor ? <a href={anchor}>{err.message}</a> : err.message}
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {serverError && (
        <div role="alert" className="form-error-summary">
          <p className="form-error-summary__body">{serverError}</p>
        </div>
      )}

      {guests.map((guest) => (
        <GuestSection
          key={guest.id}
          guest={guest}
          response={responses[guest.id]}
          errors={errors.filter((e) => e.guest_id === guest.id)}
          mealChoices={mealChoices}
          onChange={(field, value) => updateResponse(guest.id, field, value)}
        />
      ))}

      <div className="rsvp-form__actions">
        <button type="submit" disabled={submitting} className="btn btn--primary">
          {submitting ? 'Sending…' : 'Send our reply'}
        </button>
        <p className="rsvp-form__actions-hint">
          You can change your answer any time before {replyByDate}.
        </p>
      </div>
    </form>
  )
}

function GuestSection({ guest, response, errors, mealChoices, onChange }) {
  const errorsByField = {}
  for (const e of errors) {
    if (e.field) errorsByField[e.field] = e
  }
  const attending = response.attending

  return (
    <section className="rsvp-form__guest" id={`guest-${guest.id}-top`}>
      <div className="rsvp-form__section">
        <h2 className="rsvp-form__greeting">Hello, {guest.name}</h2>
      </div>

      <fieldset className="rsvp-form__section" style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="rsvp-form__section-title">Will you be joining us?</legend>
        <div className="choice-cards" role="radiogroup" aria-label={`RSVP for ${guest.name}`}>
          <ChoiceCard
            selected={attending === true}
            onSelect={() => onChange('attending', true)}
            primary="Joyfully accepts"
            secondary="Wouldn't miss it"
          />
          <ChoiceCard
            selected={attending === false}
            onSelect={() => onChange('attending', false)}
            primary="Regretfully declines"
            secondary="We'll miss you"
          />
        </div>
      </fieldset>

      {attending === true && (
        <>
          <hr className="rsvp-form__divider" />
          <div className="rsvp-form__section" id={`guest-${guest.id}-meal_choice`}>
            <label
              htmlFor={`guest-${guest.id}-meal`}
              className={
                'rsvp-form__section-title' +
                (errorsByField.meal_choice ? ' rsvp-form__section-title--error' : '')
              }
            >
              Your dinner
            </label>
            <select
              id={`guest-${guest.id}-meal`}
              className={
                'form-select' + (errorsByField.meal_choice ? ' form-select--error' : '')
              }
              value={response.meal_choice}
              onChange={(e) => onChange('meal_choice', e.target.value)}
            >
              <option value="">Choose one…</option>
              {mealChoices.map((mc) => (
                <option key={mc.value} value={mc.value}>
                  {mc.label}
                </option>
              ))}
            </select>
            {errorsByField.meal_choice && (
              <div className="form-help form-help--error">{errorsByField.meal_choice.message}</div>
            )}
          </div>

          {guest.plusOneAllowed && (
            <>
              <hr className="rsvp-form__divider" />
              <div className="plus-one-block">
                <div className="plus-one-block__intro">
                  <div className="plus-one-block__title">Bringing someone?</div>
                  <p className="plus-one-block__body">Your invitation allows one guest.</p>
                </div>
                <div className="choice-cards" role="radiogroup" aria-label="Plus one">
                  <ChoiceCard
                    compact
                    selected={response.plus_one_attending === true}
                    onSelect={() => onChange('plus_one_attending', true)}
                    primary="Yes, one guest"
                  />
                  <ChoiceCard
                    compact
                    selected={response.plus_one_attending === false}
                    onSelect={() => onChange('plus_one_attending', false)}
                    primary="Coming alone"
                  />
                </div>
                <div className="plus-one-block__fields" id={`guest-${guest.id}-plus_one_name`}>
                  <label
                    htmlFor={`guest-${guest.id}-plus1-name`}
                    className={
                      'form-label' + (errorsByField.plus_one_name ? ' form-label--error' : '')
                    }
                  >
                    Their name
                  </label>
                  <input
                    id={`guest-${guest.id}-plus1-name`}
                    className={
                      'form-input' + (errorsByField.plus_one_name ? ' form-input--error' : '')
                    }
                    disabled={!response.plus_one_attending}
                    value={response.plus_one_name}
                    onChange={(e) => onChange('plus_one_name', e.target.value)}
                    placeholder="First and last name"
                    autoComplete="off"
                  />
                  {errorsByField.plus_one_name && (
                    <div className="form-help form-help--error">
                      {errorsByField.plus_one_name.message}
                    </div>
                  )}
                </div>
                <div className="plus-one-block__fields" id={`guest-${guest.id}-plus_one_meal`}>
                  <label
                    htmlFor={`guest-${guest.id}-plus1-meal`}
                    className={
                      'form-label' + (errorsByField.plus_one_meal ? ' form-label--error' : '')
                    }
                  >
                    Their dinner
                  </label>
                  <select
                    id={`guest-${guest.id}-plus1-meal`}
                    className={
                      'form-select' + (errorsByField.plus_one_meal ? ' form-select--error' : '')
                    }
                    disabled={!response.plus_one_attending}
                    value={response.plus_one_meal}
                    onChange={(e) => onChange('plus_one_meal', e.target.value)}
                  >
                    <option value="">Choose one…</option>
                    {mealChoices.map((mc) => (
                      <option key={mc.value} value={mc.value}>
                        {mc.label}
                      </option>
                    ))}
                  </select>
                  {errorsByField.plus_one_meal && (
                    <div className="form-help form-help--error">
                      {errorsByField.plus_one_meal.message}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </>
      )}

      <hr className="rsvp-form__divider" />
      <div className="rsvp-form__section">
        <label className="form-label" htmlFor={`guest-${guest.id}-notes`}>
          Anything we should know? <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>(optional)</span>
        </label>
        <textarea
          id={`guest-${guest.id}-notes`}
          className="form-textarea"
          placeholder="Allergies, dietary needs, a song you need to hear…"
          value={response.notes}
          onChange={(e) => onChange('notes', e.target.value)}
        />
      </div>
    </section>
  )
}

function ChoiceCard({ selected, onSelect, primary, secondary, compact }) {
  return (
    <button
      type="button"
      className={'choice-card' + (compact ? ' choice-card--compact' : '')}
      data-selected={selected ? 'true' : 'false'}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="choice-card__primary">{primary}</span>
      {secondary && <span className="choice-card__secondary">{secondary}</span>}
    </button>
  )
}

function Receipt({ receipt, onEdit }) {
  const attendingRows = receipt.filter((r) => r.attending)
  const seatsTotal = attendingRows.reduce((n, r) => n + 1 + (r.plus_one_attending ? 1 : 0), 0)
  const anyAttending = seatsTotal > 0

  const title = anyAttending ? "We'll see you in the canyon." : 'Thank you for letting us know.'
  const lede = anyAttending
    ? `${words(seatsTotal)} seat${seatsTotal === 1 ? '' : 's'} saved. We'll send directions and a timeline the week before.`
    : "We'll miss you — safe travels wherever the day finds you."

  return (
    <div className="rsvp-receipt">
      <div className="rsvp-receipt__hero">
        <div className="rsvp-receipt__hero-icon" aria-hidden="true">✓</div>
        <div className="rsvp-receipt__hero-eyebrow">Reply received</div>
        <h2 className="rsvp-receipt__hero-title">{title}</h2>
        <p className="rsvp-receipt__hero-lede">{lede}</p>
      </div>
      <div className="rsvp-receipt__list">
        {receipt.map((r) => (
          <ReceiptRow key={r.guest_id} rsvp={r} />
        ))}
      </div>
      <div className="rsvp-receipt__actions">
        <button type="button" className="btn btn--secondary" onClick={onEdit}>
          Change our answer
        </button>
        <a href="/travel/" className="rsvp-receipt__link">Travel &amp; hotels →</a>
      </div>
    </div>
  )
}

function ReceiptRow({ rsvp }) {
  const value = rsvp.attending
    ? [rsvp.meal_choice_label || 'Yes', rsvp.plus_one_attending ? `+ ${rsvp.plus_one_name || 'guest'} (${rsvp.plus_one_meal_label || '—'})` : '']
        .filter(Boolean)
        .join(' · ')
    : 'Regretfully declines'
  return (
    <div className="rsvp-receipt__row">
      <span className="rsvp-receipt__row-label">{rsvp.guest_name}</span>
      <span className="rsvp-receipt__row-value">{value}</span>
    </div>
  )
}
