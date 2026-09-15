/**
 * Interactive, zoomable Google Map for the Delivery Partner's route planner.
 * Renders origin + numbered stop markers + optional polyline.
 *
 * Cross-platform strategy:
 *   • iOS/Android → react-native-webview loads an HTML shell containing Google Maps JS.
 *   • Web          → renders a plain <iframe srcDoc={html}> since react-native-webview
 *                     does not have a web build.
 *
 * The HTML uses `libraries=geometry` for decoding the encoded polyline that the
 * backend returns from Google Directions.
 */
import React, { useMemo } from "react";
import { Platform, View, StyleSheet, ActivityIndicator } from "react-native";
import { WebView } from "react-native-webview";

export type MapStop = {
  lat: number;
  lng: number;
  label: string;   // "A", "B", "C" — shown inside the marker
  title?: string;  // hover/title text
};

export function RouteMap({
  origin,
  stops,
  polyline,
  height = 280,
  originLabel = "S",
  originTitle = "Start",
}: {
  origin: { lat: number; lng: number };
  stops: MapStop[];
  polyline?: string | null;
  height?: number;
  originLabel?: string;
  originTitle?: string;
}) {
  const apiKey = process.env.EXPO_PUBLIC_GOOGLE_MAPS_API_KEY || "";
  const html = useMemo(
    () => buildMapHtml({ apiKey, origin, stops, polyline: polyline || null, originLabel, originTitle }),
    [apiKey, origin, stops, polyline, originLabel, originTitle],
  );

  if (!apiKey) {
    return (
      <View style={[styles.wrap, { height, alignItems: "center", justifyContent: "center" }]}>
        <ActivityIndicator />
      </View>
    );
  }

  if (Platform.OS === "web") {
    // React Native Web can render a raw HTML element — use createElement to avoid
    // TypeScript/RN complaints about `iframe` not being a valid RN component.
    return (
      <View style={[styles.wrap, { height }]}>
        {React.createElement("iframe", {
          srcDoc: html,
          style: { border: 0, width: "100%", height: "100%" },
          sandbox: "allow-scripts allow-same-origin allow-popups",
          allow: "geolocation",
          title: "Delivery route map",
        })}
      </View>
    );
  }

  return (
    <View style={[styles.wrap, { height }]}>
      <WebView
        originWhitelist={["*"]}
        source={{ html }}
        style={styles.webview}
        containerStyle={{ backgroundColor: "transparent" }}
        javaScriptEnabled
        domStorageEnabled
        scrollEnabled={false}
        setBuiltInZoomControls={false}
        startInLoadingState
        renderLoading={() => (
          <View style={styles.loading}><ActivityIndicator /></View>
        )}
      />
    </View>
  );
}

// ----------------------------------------------------------------------
// HTML shell
// ----------------------------------------------------------------------
function buildMapHtml({
  apiKey, origin, stops, polyline, originLabel, originTitle,
}: {
  apiKey: string;
  origin: { lat: number; lng: number };
  stops: MapStop[];
  polyline: string | null;
  originLabel: string;
  originTitle: string;
}): string {
  const stopsJson = JSON.stringify(stops);
  const originJson = JSON.stringify(origin);
  // The polyline may contain backslashes — escape for safe embedding as a JS string literal.
  const polyEscaped = polyline
    ? polyline.replace(/\\/g, "\\\\").replace(/'/g, "\\'")
    : "";

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
<style>
  html,body,#map { margin:0; padding:0; height:100%; width:100%; background:#f3f4f6; }
  body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }
</style>
</head>
<body>
<div id="map"></div>
<script>
  const STOPS = ${stopsJson};
  const ORIGIN = ${originJson};
  const POLY = '${polyEscaped}';
  function initMap() {
    const map = new google.maps.Map(document.getElementById('map'), {
      zoom: 11,
      center: ORIGIN,
      disableDefaultUI: false,
      zoomControl: true,
      gestureHandling: 'greedy',
      streetViewControl: false,
      mapTypeControl: false,
      fullscreenControl: false,
      clickableIcons: false,
    });
    const bounds = new google.maps.LatLngBounds();

    // Start marker
    new google.maps.Marker({
      position: ORIGIN,
      map,
      title: '${originTitle.replace(/'/g, "\\'")}',
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 13,
        fillColor: '#00A651',
        fillOpacity: 1,
        strokeColor: '#ffffff',
        strokeWeight: 3,
      },
      label: { text: '${originLabel.replace(/'/g, "\\'")}', color: '#ffffff', fontWeight: '700', fontSize: '12px' },
      zIndex: 999,
    });
    bounds.extend(ORIGIN);

    STOPS.forEach((s) => {
      new google.maps.Marker({
        position: { lat: s.lat, lng: s.lng },
        map,
        title: s.title || ('Stop ' + s.label),
        icon: {
          path: google.maps.SymbolPath.CIRCLE,
          scale: 14,
          fillColor: '#B14F36',
          fillOpacity: 1,
          strokeColor: '#ffffff',
          strokeWeight: 3,
        },
        label: { text: s.label, color: '#ffffff', fontWeight: '700', fontSize: '12px' },
      });
      bounds.extend({ lat: s.lat, lng: s.lng });
    });

    if (POLY) {
      try {
        const path = google.maps.geometry.encoding.decodePath(POLY);
        new google.maps.Polyline({
          path,
          map,
          geodesic: false,
          strokeColor: '#00A651',
          strokeOpacity: 0.95,
          strokeWeight: 5,
        });
      } catch (e) { console.log('polyline decode error', e); }
    }
    if (STOPS.length > 0) {
      map.fitBounds(bounds, 48);
    } else {
      map.setZoom(11);
    }
  }
  window.initMap = initMap;
</script>
<script async src="https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=geometry&callback=initMap"></script>
</body></html>`;
}

const styles = StyleSheet.create({
  wrap: {
    width: "100%",
    borderRadius: 12,
    overflow: "hidden",
    backgroundColor: "#f3f4f6",
  },
  webview: { flex: 1, backgroundColor: "transparent" },
  loading: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center" },
});
