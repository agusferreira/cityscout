"use client";

import { useEffect, useRef } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// ── Types ──

export interface MapPin {
  name: string;
  lat: number;
  lng: number;
  category: string;
  why: string;
  source_url?: string;
}

interface CityMapProps {
  center: { lat: number; lng: number; zoom?: number };
  pins: MapPin[];
}

// ── Category Colors ──

const CATEGORY_COLORS: Record<string, string> = {
  coffee: "#8B4513",
  food: "#DC143C",
  nightlife: "#9B59B6",
  culture: "#3498DB",
  fitness: "#27AE60",
  neighborhoods: "#F39C12",
};

const CATEGORY_EMOJI: Record<string, string> = {
  coffee: "☕",
  food: "🍽️",
  nightlife: "🌙",
  culture: "🎨",
  fitness: "🏃",
  neighborhoods: "🏘️",
};

// ── Custom Marker Icons ──

function createCategoryIcon(category: string): L.DivIcon {
  const color = CATEGORY_COLORS[category] || "#6366f1";
  const emoji = CATEGORY_EMOJI[category] || "📍";

  return L.divIcon({
    html: `<div style="
      background: ${color};
      width: 32px;
      height: 32px;
      border-radius: 50% 50% 50% 0;
      transform: rotate(-45deg);
      display: flex;
      align-items: center;
      justify-content: center;
      border: 2px solid white;
      box-shadow: 0 2px 8px rgba(0,0,0,0.4);
    ">
      <span style="transform: rotate(45deg); font-size: 14px; line-height: 1;">${emoji}</span>
    </div>`,
    className: "custom-pin",
    iconSize: [32, 32],
    iconAnchor: [16, 32],
    popupAnchor: [0, -32],
  });
}

// ── FitBounds Component ──

function FitBoundsToMarkers({ pins }: { pins: MapPin[] }) {
  const map = useMap();

  useEffect(() => {
    if (pins.length === 0) return;
    const bounds = L.latLngBounds(
      pins.map((p) => [p.lat, p.lng] as [number, number])
    );
    map.fitBounds(bounds, { padding: [50, 50], maxZoom: 15 });
  }, [pins, map]);

  return null;
}

// ── Category Badge for Popup ──

function categoryBadgeHtml(category: string): string {
  const color = CATEGORY_COLORS[category] || "#6366f1";
  const emoji = CATEGORY_EMOJI[category] || "📍";
  return `<span style="
    display: inline-flex;
    align-items: center;
    gap: 4px;
    background: ${color}22;
    color: ${color};
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
  ">${emoji} ${category}</span>`;
}

// ── Main Component ──

export default function CityMap({ center, pins }: CityMapProps) {
  return (
    <MapContainer
      center={[center.lat, center.lng]}
      zoom={center.zoom || 13}
      className="h-full w-full"
      zoomControl={false}
      style={{ background: "#1a1a2e" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://carto.com/">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />

      {pins.map((pin, idx) => (
        <Marker
          key={`${pin.name}-${idx}`}
          position={[pin.lat, pin.lng]}
          icon={createCategoryIcon(pin.category)}
        >
          <Popup maxWidth={280} className="dark-popup">
            <div style={{
              fontFamily: "system-ui, sans-serif",
              color: "#fafafa",
              background: "#18181b",
              margin: "-14px -20px",
              padding: "16px",
              borderRadius: "8px",
              minWidth: "220px",
            }}>
              <h3 style={{
                fontSize: "15px",
                fontWeight: 700,
                marginBottom: "6px",
                color: "#fafafa",
              }}>
                {pin.name}
              </h3>
              <div
                style={{ marginBottom: "8px" }}
                dangerouslySetInnerHTML={{
                  __html: categoryBadgeHtml(pin.category),
                }}
              />
              <p style={{
                fontSize: "12px",
                lineHeight: "1.5",
                color: "#a1a1aa",
                margin: 0,
              }}>
                {pin.why}
              </p>
              {pin.source_url && (
                <a
                  href={pin.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    display: "inline-block",
                    marginTop: "8px",
                    fontSize: "11px",
                    color: "#6366f1",
                  }}
                >
                  Source →
                </a>
              )}
            </div>
          </Popup>
        </Marker>
      ))}

      <FitBoundsToMarkers pins={pins} />
    </MapContainer>
  );
}
