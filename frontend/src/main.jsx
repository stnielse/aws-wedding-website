import { createRoot } from 'react-dom/client'
import RsvpForm from './RsvpForm'
import Gallery from './Gallery'

const rsvpRoot = document.getElementById('rsvp-root')
if (rsvpRoot) {
  const props = JSON.parse(document.getElementById('rsvp-data').textContent)
  createRoot(rsvpRoot).render(<RsvpForm {...props} />)
}

const galleryRoot = document.getElementById('gallery-root')
if (galleryRoot) {
  const props = JSON.parse(document.getElementById('gallery-data').textContent)
  createRoot(galleryRoot).render(<Gallery {...props} />)
}
