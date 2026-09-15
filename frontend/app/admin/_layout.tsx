import React from "react";
import { Stack } from "expo-router";

export default function AdminLayout() {
  return (
    <Stack screenOptions={{ headerShown: false, animation: "fade" }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="dashboard" />
      <Stack.Screen name="master-menu" />
      <Stack.Screen name="menu" />
      <Stack.Screen name="catering" />
      <Stack.Screen name="orders" />
      <Stack.Screen name="billing" />
      <Stack.Screen name="settings" />
    </Stack>
  );
}
