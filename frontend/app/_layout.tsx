import { Stack, useRouter, usePathname } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { useEffect } from "react";
import { LogBox, Platform } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import * as Notifications from "expo-notifications";
import * as Linking from "expo-linking";
import Constants from "expo-constants";

import { useIconFonts } from "@/src/hooks/use-icon-fonts";
import { AuthProvider } from "@/src/auth";
import { CartProvider } from "@/src/cart";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync();

// Which app variant are we running? Set at build time via APP_VARIANT env
// in app.config.js (values: "customer" | "delivery").
export const APP_VARIANT: "customer" | "delivery" =
  ((Constants.expoConfig?.extra as any)?.appVariant as any) || "customer";

// Push: module-scope config (guard web)
if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    } as any),
  });
}
if (Platform.OS === "android") {
  Notifications.setNotificationChannelAsync("default", {
    name: "Default",
    importance: Notifications.AndroidImportance.MAX,
    sound: "default",
  });
}

export default function RootLayout() {
  const [loaded, error] = useIconFonts();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (loaded || error) SplashScreen.hideAsync();
  }, [loaded, error]);

  // -------- Variant routing enforcement --------
  //  * DELIVERY variant native builds → only the /delivery-partner flow is
  //    reachable. Any other deep link is redirected there.
  //  * CUSTOMER variant STANDALONE native builds → admin/delivery routes hidden.
  //  * Expo Go dev + web preview → everything reachable for QA.
  useEffect(() => {
    if (!loaded && !error) return;
    if (!pathname) return;
    const p = pathname;
    // Detect Expo Go vs standalone build. Expo Go should behave like preview
    // (both flows reachable) so users can test both apps from one QR code.
    const isExpoGo = (Constants as any).appOwnership === "expo";
    // Defer to next tick — the Stack navigator must mount before we can call replace().
    const t = setTimeout(() => {
      if (APP_VARIANT === "delivery") {
        // Standalone Delivery app: force everything to /delivery-partner.
        if (!p.startsWith("/delivery-partner")) {
          router.replace("/delivery-partner");
        }
        return;
      }
      // Customer variant standalone native build: hide /admin only.
      // /delivery-partner remains reachable so real delivery partners can sign
      // in via the small "Delivery partner? Sign in here" link on the login screen.
      // (Expo Go and web preview leave everything reachable regardless.)
      if (Platform.OS !== "web" && !isExpoGo) {
        if (p.startsWith("/admin")) {
          router.replace("/");
        }
      }
    }, 0);
    return () => clearTimeout(t);
  }, [loaded, error, pathname, router]);

  useEffect(() => {
    if (Platform.OS === "web") return;
    const tapSub = Notifications.addNotificationResponseReceivedListener((response) => {
      const data: any = response.notification.request.content.data || {};
      const url = data.deeplink || data.action_url;
      if (!url) return;
      if (typeof url === "string" && url.startsWith("http")) Linking.openURL(url);
      else router.push(url);
    });
    Notifications.getLastNotificationResponseAsync().then((response) => {
      if (!response) return;
      const data: any = response.notification.request.content.data || {};
      const url = data.deeplink || data.action_url;
      if (!url) return;
      if (typeof url === "string" && url.startsWith("http")) Linking.openURL(url);
      else router.push(url);
    });
    return () => {
      tapSub.remove();
    };
  }, [router]);

  if (!loaded && !error) return null;

  return (
    <SafeAreaProvider>
      <AuthProvider>
        <CartProvider>
          <Stack screenOptions={{ headerShown: false, animation: "slide_from_right" }}>
            <Stack.Screen name="index" />
            <Stack.Screen name="login" />
            <Stack.Screen name="email-auth" />
            <Stack.Screen name="invite" />
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="cart" options={{ presentation: "modal" }} />
            <Stack.Screen name="order/[id]" />
            <Stack.Screen name="catering/[id]" />
            <Stack.Screen name="menu/package/[id]" />
            <Stack.Screen name="review/[token]" />
            <Stack.Screen name="delivery-partner" />
          </Stack>
        </CartProvider>
      </AuthProvider>
    </SafeAreaProvider>
  );
}
