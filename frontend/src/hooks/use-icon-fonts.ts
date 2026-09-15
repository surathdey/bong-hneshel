// Icon font loader. With @react-native-vector-icons the .ttf ships inside the
// package and is registered via expo-font. Preloading it here keeps the
// [loaded, error] contract the root layout relies on to gate the splash screen,
// so icons are ready before the first frame paints (Expo Go, native and web).
// Usage: const [loaded, error] = useIconFonts();

import { useFonts } from "expo-font";

export const useIconFonts = (): readonly [boolean, Error | null] =>
  useFonts({
    Ionicons: require("@react-native-vector-icons/ionicons/fonts/Ionicons.ttf"),
  });
