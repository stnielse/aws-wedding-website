export default function Gallery(props) {
  return (
    <div>
      <p>Gallery island mounted.</p>
      <pre>{JSON.stringify(props, null, 2)}</pre>
    </div>
  )
}
