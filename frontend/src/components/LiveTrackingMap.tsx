/**
 * Uber-style live tracking map for the customer's order screen.
 *
 * Key differences from `RouteMap`:
 *   • HTML is memoized ONCE (per destination) — never re-renders while the
 *     driver moves. Instead the marker is animated via `injectJavaScript`
 *     (native) / `postMessage` (web iframe), so the map is smooth like Uber.
 *   • Camera auto-follows the driver with a gentle panTo animation.
 *   • Bearing is derived from the last-known → new position so the car icon
 *     rotates towards the direction of travel (nice touch).
 *
 * Contract:
 *   <LiveTrackingMap
 *      driver={{ lat, lng }}          // updates every poll — smoothly animated
 *      destination={{ lat, lng, address? }}   // static
 *      polyline={string | null}       // static route driver→home
 *      height={220}
 *   />
 */
import React, { useEffect, useMemo, useRef } from "react";
import { Platform, View, StyleSheet, ActivityIndicator } from "react-native";
import { WebView } from "react-native-webview";

type LatLng = { lat: number; lng: number };

export function LiveTrackingMap({
  driver,
  destination,
  polyline,
  height = 220,
}: {
  driver: LatLng | null | undefined;
  destination: LatLng & { address?: string };
  polyline?: string | null;
  height?: number;
}) {
  const apiKey = process.env.EXPO_PUBLIC_GOOGLE_MAPS_API_KEY || "";
  const webviewRef = useRef<WebView>(null);
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const lastDriverRef = useRef<LatLng | null>(null);

  // The HTML is built ONCE per destination — driver updates never re-render it.
  const html = useMemo(
    () => buildLiveHtml({ apiKey, destination, polyline: polyline || null, initialDriver: driver || null }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [apiKey, destination.lat, destination.lng, polyline],
  );

  // Push driver-position updates into the map via JS bridge.
  useEffect(() => {
    if (!driver || driver.lat == null || driver.lng == null) return;
    const prev = lastDriverRef.current;
    lastDriverRef.current = driver;
    const bearing = prev ? computeBearing(prev, driver) : 0;
    const payload = JSON.stringify({ type: "driver", lat: driver.lat, lng: driver.lng, bearing });
    const js = `try{window.__applyUpdate(${payload});}catch(e){} true;`;

    if (Platform.OS === "web") {
      // Web fallback: postMessage into the iframe.
      try {
        iframeRef.current?.contentWindow?.postMessage(payload, "*");
      } catch { /* ignore */ }
    } else {
      webviewRef.current?.injectJavaScript(js);
    }
  }, [driver?.lat, driver?.lng]);

  if (!apiKey) {
    return (
      <View style={[styles.wrap, { height, alignItems: "center", justifyContent: "center" }]}>
        <ActivityIndicator />
      </View>
    );
  }

  if (Platform.OS === "web") {
    return (
      <View style={[styles.wrap, { height }]}>
        {React.createElement("iframe", {
          ref: (el: HTMLIFrameElement | null) => { iframeRef.current = el; },
          srcDoc: html,
          style: { border: 0, width: "100%", height: "100%" },
          sandbox: "allow-scripts allow-same-origin",
          title: "Live delivery tracking",
        })}
      </View>
    );
  }

  return (
    <View style={[styles.wrap, { height }]}>
      <WebView
        ref={webviewRef}
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

// Turn two lat/lng into a compass bearing in degrees (0=N, 90=E, 180=S, 270=W).
// Useful so the car marker rotates in the direction it's moving.
function computeBearing(a: LatLng, b: LatLng): number {
  const toRad = (d: number) => (d * Math.PI) / 180;
  const toDeg = (r: number) => (r * 180) / Math.PI;
  const φ1 = toRad(a.lat), φ2 = toRad(b.lat);
  const λ1 = toRad(a.lng), λ2 = toRad(b.lng);
  const y = Math.sin(λ2 - λ1) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(λ2 - λ1);
  return (toDeg(Math.atan2(y, x)) + 360) % 360;
}

function buildLiveHtml({
  apiKey, destination, polyline, initialDriver,
}: {
  apiKey: string;
  destination: LatLng & { address?: string };
  polyline: string | null;
  initialDriver: LatLng | null;
}): string {
  const destJson = JSON.stringify(destination);
  const initJson = JSON.stringify(initialDriver);
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
  var DEST = ${destJson};
  var INITIAL_DRIVER = ${initJson};
  var POLY = '${polyEscaped}';

  var map = null;
  var driverMarker = null;
  var animTimer = null;
  var lastPos = null;   // {lat,lng}
  var following = true; // camera auto-follows driver

  function initMap() {
    map = new google.maps.Map(document.getElementById('map'), {
      zoom: 14,
      center: INITIAL_DRIVER || DEST,
      disableDefaultUI: false,
      zoomControl: true,
      gestureHandling: 'greedy',
      streetViewControl: false,
      mapTypeControl: false,
      fullscreenControl: false,
      clickableIcons: false,
    });

    // Home / destination marker (fixed).
    new google.maps.Marker({
      position: DEST,
      map: map,
      title: DEST.address || 'Delivery address',
      icon: {
        path: google.maps.SymbolPath.CIRCLE,
        scale: 12,
        fillColor: '#B14F36',
        fillOpacity: 1,
        strokeColor: '#ffffff',
        strokeWeight: 3,
      },
      label: { text: 'H', color: '#ffffff', fontWeight: '700', fontSize: '12px' },
    });

    // Optional pre-computed route polyline (driver → home).
    if (POLY) {
      try {
        var path = google.maps.geometry.encoding.decodePath(POLY);
        new google.maps.Polyline({
          path: path, map: map, geodesic: false,
          strokeColor: '#00A651', strokeOpacity: 0.9, strokeWeight: 5,
        });
      } catch (e) { /* swallow */ }
    }

    // If we already have the driver's starting position, drop the pin now.
    if (INITIAL_DRIVER && INITIAL_DRIVER.lat != null) {
      placeDriver(INITIAL_DRIVER.lat, INITIAL_DRIVER.lng, 0);
      fitBoth();
    }

    // Detach camera-follow the moment the user pans, so we don't fight them.
    map.addListener('dragstart', function () { following = false; });
  }

  // Build/refresh the driver marker. Uses a green circle with a rotated
  // triangle inside for a directional feel (bearing == direction of travel).
  function placeDriver(lat, lng, bearing) {
    var pos = { lat: lat, lng: lng };
    if (!driverMarker) {
      driverMarker = new google.maps.Marker({
        position: pos,
        map: map,
        title: 'Driver',
        icon: {
          path: 'M 0,-8 L 5,4 L 0,1 L -5,4 Z',  // arrow-triangle
          fillColor: '#00A651',
          fillOpacity: 1,
          strokeColor: '#ffffff',
          strokeWeight: 2,
          scale: 2,
          rotation: bearing || 0,
          anchor: new google.maps.Point(0, 0),
        },
        zIndex: 999,
      });
    } else {
      // Animate towards new position over ~1.2s so it feels smooth.
      animateMarker(driverMarker, driverMarker.getPosition(), pos, 1200);
      // Rotate the icon towards direction of travel.
      var icon = driverMarker.getIcon();
      if (icon && typeof icon === 'object') {
        icon.rotation = bearing || 0;
        driverMarker.setIcon(icon);
      }
    }
    lastPos = pos;
  }

  function animateMarker(marker, from, to, durMs) {
    if (animTimer) { clearInterval(animTimer); animTimer = null; }
    var startLat = from.lat(), startLng = from.lng();
    var deltaLat = to.lat - startLat, deltaLng = to.lng - startLng;
    var steps = 24, i = 0;
    animTimer = setInterval(function () {
      i += 1;
      var t = i / steps;
      // easeInOut
      var eased = t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
      marker.setPosition({
        lat: startLat + deltaLat * eased,
        lng: startLng + deltaLng * eased,
      });
      if (following && map) map.panTo(marker.getPosition());
      if (i >= steps) { clearInterval(animTimer); animTimer = null; }
    }, durMs / 24);
  }

  function fitBoth() {
    if (!map || !lastPos) return;
    var b = new google.maps.LatLngBounds();
    b.extend(lastPos);
    b.extend(DEST);
    map.fitBounds(b, 60);
  }

  // Unified update entry point — called by RN (injectJavaScript) and web (postMessage).
  window.__applyUpdate = function (payload) {
    try {
      var msg = typeof payload === 'string' ? JSON.parse(payload) : payload;
      if (msg && msg.type === 'driver' && msg.lat != null && msg.lng != null) {
        placeDriver(msg.lat, msg.lng, msg.bearing || 0);
      }
    } catch (e) { /* ignore */ }
  };

  // Web iframe: listen for postMessage.
  window.addEventListener('message', function (ev) {
    window.__applyUpdate(ev.data);
  });

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
