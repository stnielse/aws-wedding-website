import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const SIZES = '(min-width: 1100px) 25vw, (min-width: 700px) 33vw, 50vw'
const LIGHTBOX_SIZES = '100vw'
const SWIPE_MIN_PX = 40
const COPY1_SUFFIX = '-copy1'

/**
 * Group each `<base>-copy1` photo with its base-slug partner into a single
 * "cell". Cells are what get rendered into the CSS multi-column grid with
 * `break-inside: avoid` — that guarantees the pair stays in one column.
 * Singletons (a photo whose partner isn't present) form a one-photo cell.
 * Assumes the input is already in sort order such that `-copy1` precedes
 * its base (ASCII: '-' < '.'), which the server enforces.
 */
function groupIntoCells(photos) {
  const cells = []
  let i = 0
  while (i < photos.length) {
    const current = photos[i]
    if (current.slug.endsWith(COPY1_SUFFIX)) {
      const baseSlug = current.slug.slice(0, -COPY1_SUFFIX.length)
      const next = photos[i + 1]
      if (next && next.slug === baseSlug) {
        cells.push({ key: current.slug, indices: [i, i + 1] })
        i += 2
        continue
      }
    }
    cells.push({ key: current.slug, indices: [i] })
    i += 1
  }
  return cells
}

export default function Gallery({ photos }) {
  const [openIndex, setOpenIndex] = useState(null)
  const isOpen = openIndex !== null
  const cells = useMemo(() => groupIntoCells(photos || []), [photos])

  const openAt = useCallback((index) => setOpenIndex(index), [])
  const close = useCallback(() => setOpenIndex(null), [])
  const prev = useCallback(
    () => setOpenIndex((i) => (i === null ? null : (i - 1 + photos.length) % photos.length)),
    [photos.length],
  )
  const next = useCallback(
    () => setOpenIndex((i) => (i === null ? null : (i + 1) % photos.length)),
    [photos.length],
  )

  useEffect(() => {
    if (!isOpen) return
    const onKey = (e) => {
      if (e.key === 'Escape') close()
      else if (e.key === 'ArrowLeft') prev()
      else if (e.key === 'ArrowRight') next()
    }
    window.addEventListener('keydown', onKey)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = prevOverflow
    }
  }, [isOpen, close, prev, next])

  if (!photos || photos.length === 0) {
    return <p className="body" style={{ textAlign: 'center', padding: '3rem 0' }}>Photos are on the way.</p>
  }

  return (
    <>
      <div className="gallery__grid">
        {cells.map((cell) => (
          <div key={cell.key} className="gallery__cell">
            {cell.indices.map((i) => {
              const photo = photos[i]
              return (
                <button
                  key={photo.id}
                  type="button"
                  className="gallery__item"
                  onClick={() => openAt(i)}
                  aria-label={photo.alt ? `Open photo: ${photo.alt}` : `Open photo ${i + 1} of ${photos.length}`}
                >
                  <img
                    className="gallery__img"
                    src={photo.src}
                    srcSet={photo.srcset}
                    sizes={SIZES}
                    width={photo.width}
                    height={photo.height}
                    loading="lazy"
                    decoding="async"
                    alt={photo.alt || ''}
                  />
                </button>
              )
            })}
          </div>
        ))}
      </div>

      {isOpen && (
        <Lightbox
          photo={photos[openIndex]}
          index={openIndex}
          total={photos.length}
          onClose={close}
          onPrev={prev}
          onNext={next}
        />
      )}
    </>
  )
}

function Lightbox({ photo, index, total, onClose, onPrev, onNext }) {
  const touchStartX = useRef(null)

  const onTouchStart = (e) => {
    touchStartX.current = e.touches[0].clientX
  }
  const onTouchEnd = (e) => {
    if (touchStartX.current === null) return
    const dx = e.changedTouches[0].clientX - touchStartX.current
    touchStartX.current = null
    if (Math.abs(dx) < SWIPE_MIN_PX) return
    if (dx > 0) onPrev()
    else onNext()
  }

  const onBackdropClick = (e) => {
    if (e.target === e.currentTarget) onClose()
  }

  return (
    <div
      className="gallery__lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={photo.alt || `Photo ${index + 1} of ${total}`}
      onClick={onBackdropClick}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      <button
        type="button"
        className="gallery__lightbox-close"
        onClick={onClose}
        aria-label="Close"
      >
        &times;
      </button>

      <button
        type="button"
        className="gallery__lightbox-nav gallery__lightbox-nav--prev"
        onClick={onPrev}
        aria-label="Previous photo"
      >
        &lsaquo;
      </button>

      <figure className="gallery__lightbox-figure">
        <img
          className="gallery__lightbox-img"
          src={photo.src}
          srcSet={photo.srcset}
          sizes={LIGHTBOX_SIZES}
          width={photo.width}
          height={photo.height}
          alt={photo.alt || ''}
        />
        {photo.caption && (
          <figcaption className="gallery__lightbox-caption">{photo.caption}</figcaption>
        )}
      </figure>

      <button
        type="button"
        className="gallery__lightbox-nav gallery__lightbox-nav--next"
        onClick={onNext}
        aria-label="Next photo"
      >
        &rsaquo;
      </button>

      <div className="gallery__lightbox-count" aria-hidden="true">
        {index + 1} / {total}
      </div>
    </div>
  )
}
