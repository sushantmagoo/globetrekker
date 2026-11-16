import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect } from 'react'
import { MapContainer, Marker, TileLayer, useMap, useMapEvents } from 'react-leaflet'

// Default marker icon, drawn as inline SVG so it doesn't depend on Leaflet's image assets.
const PIN = L.divIcon({
  className: 'map-pin',
  html: `<svg width="28" height="40" viewBox="0 0 28 40" aria-hidden="true"><path d="M14 0C6.3 0 0 6.2 0 13.9 0 24.3 14 40 14 40s14-15.7 14-26.1C28 6.2 21.7 0 14 0z" fill="#4f7a28"/><circle cx="14" cy="14" r="5.5" fill="#e8d86a"/></svg>`,
  iconSize: [28, 40],
  iconAnchor: [14, 40],
})

const TILE_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

export interface LatLng {
  lat: number
  lng: number
}

function ClickHandler({ onPick }: { onPick: (p: LatLng) => void }) {
  useMapEvents({ click: (e) => onPick({ lat: e.latlng.lat, lng: e.latlng.lng }) })
  return null
}

function Recenter({ point }: { point: LatLng | null }) {
  const map = useMap()
  useEffect(() => {
    if (point) map.setView([point.lat, point.lng], Math.max(map.getZoom(), 5))
  }, [map, point])
  return null
}

interface Props {
  point: LatLng | null
  onPick?: (p: LatLng) => void
  height?: number
  zoom?: number
}

export function PlaceMap({ point, onPick, height = 280, zoom }: Props) {
  const center: [number, number] = point ? [point.lat, point.lng] : [20, 0]
  return (
    <div className="place-map" style={{ height }}>
      <MapContainer
        center={center}
        zoom={zoom ?? (point ? 6 : 2)}
        scrollWheelZoom={Boolean(onPick)}
        dragging
        style={{ height: '100%', width: '100%' }}
        worldCopyJump
      >
        <TileLayer url={TILE_URL} attribution={ATTRIBUTION} />
        {point && <Marker position={[point.lat, point.lng]} icon={PIN} />}
        {onPick && <ClickHandler onPick={onPick} />}
        {onPick && <Recenter point={point} />}
      </MapContainer>
    </div>
  )
}
