import type { CapacitorConfig } from "@capacitor/cli";

// Test build (default): http scheme + cleartext so the phone can reach http://<PC-IP>:8000 on the same Wi-Fi.
// Release build: set CAP_RELEASE=1 before `npm run app:sync` and use an https server address.
const release = process.env.CAP_RELEASE === "1";

const config: CapacitorConfig = {
  appId: "com.skillforge.learning",
  appName: "Skill Learning",
  webDir: "dist",
  server: { androidScheme: release ? "https" : "http", cleartext: !release },
};

export default config;
