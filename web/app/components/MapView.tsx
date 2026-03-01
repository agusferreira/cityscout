"use client";

import { useEffect, useRef, useState } from "react";

// Leaflet types — we import dynamically since Leaflet needs window
interface Venue {
  name: string;
  neighborhood: string;
  lat: number;
  lng: number;
  category: string;
  source_url?: string;
  source_type?: string;
  reason?: string;
}

interface MapViewProps {
  center: { lat: number; lng: number; zoom?: number };
  venues: Venue[];
  onVenueClick?: (venue: Venue) => void;
}

const CATEGORY_COLORS: Record<string, string> = {
  coffee: "#b4783c",
  food: "#ef4444",
  nightlife: "#a855f7",
  culture: "#3b82f6",
  neighborhoods: "#22c55e",
  fitness: "#f59e0b",
};

const CATEGORY_EMOJI: Record<string, string> = {
  coffee: "☕",
  food: "🍽️",
  nightlife: "🎵",
  culture: "🎨",
  neighborhoods: "🏘️",
  fitness: "🏃",
};

export default function MapView({ center, venues, onVenueClick }: MapViewProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<any>(null);
  const markersRef = useRef<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);

  // Get unique categories
  const categories = [...new Set(venues.map((v) => v.category))].sort();

  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    // Dynamic import of Leaflet (needs window)
    const initMap = async () => {
      const L = (await import("leaflet")).default;

      // Fix default marker icons
      // @ts-ignore
      delete L.Icon.Default.prototype._getIconUrl;
      L.Icon.Default.mergeOptions({
        iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
        iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
        shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      });

      const map = L.map(mapRef.current!, {
        zoomControl: true,
        scrollWheelZoom: true,
      }).setView([center.lat, center.lng], center.zoom || 13);

      // Dark tile layer matching our theme
      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>',
        maxZoom: 19,
      }).addTo(map);

      mapInstanceRef.current = map;
      setLoaded(true);
    };

    initMap();

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
      }
    };
  }, [center]);

  // Update markers when venues or filter changes
  useEffect(() => {
    if (!mapInstanceRef.current || !loaded) return;

    const L = require("leaflet");
    const map = mapInstanceRef.current;

    // Clear existing markers
    markersRef.current.forEach((m) => map.removeLayer(m));
    markersRef.current = [];

    const filteredVenues = activeCategory
      ? venues.filter((v) => v.category === activeCategory)
      : venues;

    // Deduplicate by name + lat/lng
    const seen = new Set<string>();
    const uniqueVenues = filteredVenues.filter((v) => {
      const key = `${v.name}-${v.lat}-${v.lng}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    uniqueVenues.forEach((venue) => {
      const color = CATEGORY_COLORS[venue.category] || "#6366f1";
      const emoji = CATEGORY_EMOJI[venue.category] || "📍";

      // Create colored circle marker
      const marker = L.circleMarker([venue.lat, venue.lng], {
        radius: 8,
        fillColor: color,
        color: "#fff",
        weight: 2,
        opacity: 1,
        fillOpacity: 0.85,
      });

      // Popup content
      const popupContent = `
        <div style="font-family: system-ui, sans-serif; min-width: 180px;">
          <div style="font-weight: 600; font-size: 14px; margin-bottom: 4px;">
            ${emoji} ${venue.name}
          </div>
          <div style="color: #a1a1aa; font-size: 12px; margin-bottom: 6px;">
            ${venue.neighborhood}
          </div>
          ${venue.reason ? `<div style="font-size: 12px; line-height: 1.4; margin-bottom: 6px;">${venue.reason}</div>` : ""}
          <div style="display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 9999px; font-size: 10px; font-weight: 500; background: ${color}22; color: ${color};">
            ${venue.category}
          </div>
        </div>
      `;

      marker.bindPopup(popupContent, {
        className: "cityscout-popup",
        maxWidth: 250,
      });

      marker.on("click", () => {
        if (onVenueClick) onVenueClick(venue);
      });

      marker.addTo(map);
      markersRef.current.push(marker);
    });

    // Fit bounds if we have venues
    if (uniqueVenues.length > 1) {
      const group = L.featureGroup(markersRef.current);
      map.fitBounds(group.getBounds().pad(0.1));
    }
  }, [venues, activeCategory, loaded]);

  return (
    <div className="flex h-full flex-col">
      {/* Category filter bar */}
      <div className="flex flex-wrap gap-1.5 border-b border-border bg-card px-3 py-2">
        <button
          onClick={() => setActiveCategory(null)}
          className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
            !activeCategory
              ? "bg-accent text-white"
              : "bg-card-hover text-muted hover:text-foreground"
          }`}
        >
          All ({venues.length})
        </button>
        {categories.map((cat) => {
          const count = venues.filter((v) => v.category === cat).length;
          return (
            <button
              key={cat}
              onClick={() => setActiveCategory(activeCategory === cat ? null : cat)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                activeCategory === cat
                  ? "text-white"
                  : "text-muted hover:text-foreground"
              }`}
              style={{
                backgroundColor:
                  activeCategory === cat
                    ? CATEGORY_COLORS[cat] || "#6366f1"
                    : "var(--card-hover)",
              }}
            >
              {CATEGORY_EMOJI[cat] || "📍"} {cat} ({count})
            </button>
          );
        })}
      </div>

      {/* Map container */}
      <div ref={mapRef} className="flex-1" style={{ minHeight: "300px" }} />
    </div>
  );
}
