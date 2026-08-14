import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

const SIZES = '(min-width: 1100px) 25vw, (min-width: 700px) 33vw, 50vw'
const LIGHTBOX_SIZES = '100vw'
const SWIPE_MIN_PX = 40
const COPY1_SUFFIX = '-copy1'
const COLUMN_BREAKPOINTS = [
  { minWidth: 1100, columns: 4 },
  { minWidth: 700, columns: 3 },
  { minWidth: 0, columns: 2 },
]

/**
 * React to the CSS breakpoints in site.css (2/3/4 cols at 0/700/1100px).
 * Kept in JS so we can distribute cells into flex columns and let
 * `justify-content: space-between` on each column align the bottom edges.
 */
function useColumnCount() {
  const pick = () => {
    if (typeof window === 'undefined') return COLUMN_BREAKPOINTS[0].columns
    const hit = COLUMN_BREAKPOINTS.find(({ minWidth }) =>
      window.matchMedia(`(min-width: ${minWidth}px)`).matches,
    )
    return hit ? hit.columns : COLUMN_BREAKPOINTS.at(-1).columns
  }
  const [n, setN] = useState(pick)
  useEffect(() => {
    const mqls = COLUMN_BREAKPOINTS
      .filter(({ minWidth }) => minWidth > 0)
      .map(({ minWidth }) => window.matchMedia(`(min-width: ${minWidth}px)`))
    const update = () => setN(pick())
    mqls.forEach((mql) => mql.addEventListener('change', update))
    return () => mqls.forEach((mql) => mql.removeEventListener('change', update))
  }, [])
  return n
}

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
  const numCols = useColumnCount()

  /**
   * Chunk cells into N contiguous columns of near-equal count. Because all
   * photos share similar aspect ratios (mostly portrait engagement shots),
   * equal cell-count columns produce nearly equal natural heights; the
   * `justify-content: space-between` on each column then absorbs any
   * residual to align the bottom edges. Purely count-based so this stays
   * O(N) and doesn't need per-photo height math.
   */
  const columns = useMemo(() => {
    const cols = Array.from({ length: numCols }, () => [])
    if (cells.length === 0) return cols
    const per = Math.ceil(cells.length / numCols)
    cells.forEach((cell, i) => {
      const col = Math.min(numCols - 1, Math.floor(i / per))
      cols[col].push(cell)
    })
    return cols
  }, [cells, numCols])

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
        {columns.map((colCells, colIndex) => (
          <div key={colIndex} className="gallery__column">
            {colCells.map((cell) => (
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
