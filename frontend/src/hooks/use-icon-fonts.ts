// Icon font loader. We ship the Ionicons .ttf inside the app's own assets/fonts
// folder (NOT the node_modules copy) and register it via expo-font. This is
// deliberate: production deploys strip node_modules, so referencing the font
// from node_modules makes it 404 in prod (icons render as empty boxes) while
// working fine in dev/preview. A top-level app asset survives the deploy.
// Preloading here also keeps the [loaded, error] contract the root layout relies
// on to gate the splash screen, so icons are ready before the first frame paints.
// Usage: const [loaded, error] = useIconFonts();

import { useFonts } from "expo-font";

export const useIconFonts = (): readonly [boolean, Error | null] =>
  useFonts({
    Ionicons: require("../../assets/fonts/Ionicons.ttf"),
  });
