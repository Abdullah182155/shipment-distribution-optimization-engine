import { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { Layers } from 'lucide-react';

// Pre-defined color palette with vibrant, distinguishable colors
const COLORS = [
  '#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', 
  '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1',
  '#dc2626', '#2563eb', '#059669', '#d97706', '#7c3aed',
  '#db2777', '#0891b2', '#ea580c', '#0d9488', '#4f46e5'
];

export default function MapVisualization({ results, runStatus }) {
  const mapRef = useRef(null);
  const containerRef = useRef(null);
  const tileLayerRef = useRef(null);
  const [showMapBackground, setShowMapBackground] = useState(true);

  useEffect(() => {
    if (!containerRef.current) return;

    // Initialize map once
    if (!mapRef.current) {
      mapRef.current = L.map(containerRef.current, {
        zoomControl: false // Custom position if needed
      }).setView([0, 0], 2);
      
      // Store tile layer but don't add immediately
      tileLayerRef.current = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
      });
      
      L.control.zoom({ position: 'topright' }).addTo(mapRef.current);
    }
  }, []);

  // Effect to handle map background toggle
  useEffect(() => {
    if (mapRef.current && tileLayerRef.current) {
      if (showMapBackground) {
        mapRef.current.addLayer(tileLayerRef.current);
      } else {
        mapRef.current.removeLayer(tileLayerRef.current);
      }
    }
  }, [showMapBackground]);

  useEffect(() => {
    if (!mapRef.current || !results || !results.couriers || results.couriers.length === 0) {
      return;
    }

    const map = mapRef.current;
    
    // Clear existing layers
    map.eachLayer((layer) => {
      if (layer instanceof L.Polygon || layer instanceof L.CircleMarker) {
        map.removeLayer(layer);
      }
    });

    const bounds = L.latLngBounds();
    const R = 6371.0; 

    // Use actual center coordinates from backend (computed from data)
    const clat = results.center_lat || 30.06;
    const clon = results.center_lon || 31.34; 

    const kmToLatLng = (x, y) => {
      const dlat = y / R;
      const dlon = x / (R * Math.cos(clat * Math.PI / 180));
      return [clat + (dlat * 180 / Math.PI), clon + (dlon * 180 / Math.PI)];
    };

    results.couriers.forEach((courier, i) => {
      const color = COLORS[i % COLORS.length];
      
      // Draw hull
      if (courier.hull_vertices && courier.hull_vertices.length >= 3) {
        const latlngs = courier.hull_vertices.map(pt => kmToLatLng(pt[0], pt[1]));
        const poly = L.polygon(latlngs, {
          color: color,
          weight: 2,
          fillColor: color,
          fillOpacity: 0.15,
          className: 'hull-polygon transition-all duration-300'
        }).addTo(map);
        
        poly.bindTooltip(`Courier ${courier.courier_id}<br/>Area: ${courier.area_km2.toFixed(2)} km²<br/>Deliveries: ${courier.n_deliveries}`);
        latlngs.forEach(ll => bounds.extend(ll));
      }

      // Draw points
      if (courier.deliveries && results.coords_km) {
        courier.deliveries.forEach(idx => {
          const pt = results.coords_km[idx];
          if (pt) {
            const ll = kmToLatLng(pt[0], pt[1]);
            L.circleMarker(ll, {
              radius: 4,
              fillColor: color,
              color: '#fff',
              weight: 1,
              fillOpacity: 0.8
            }).addTo(map);
            bounds.extend(ll);
          }
        });
      }
    });

    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [20, 20] });
    }

  }, [results]);

  return (
    <div className={`w-full h-full relative z-0 ${!showMapBackground ? 'bg-slate-900' : ''}`}>
      <div ref={containerRef} className="w-full h-full absolute inset-0 bg-transparent transition-colors duration-300" />
      <button 
        onClick={() => setShowMapBackground(!showMapBackground)}
        className="absolute bottom-4 left-4 z-[1000] bg-slate-800/80 hover:bg-slate-700/80 backdrop-blur-md text-white border border-slate-600 px-3 py-2 rounded-lg shadow-lg flex items-center gap-2 transition-all text-sm font-medium"
      >
        <Layers size={16} className={showMapBackground ? "text-blue-400" : "text-slate-400"} />
        {showMapBackground ? 'Hide Tile Map' : 'Show Tile Map'}
      </button>
    </div>
  );
}
