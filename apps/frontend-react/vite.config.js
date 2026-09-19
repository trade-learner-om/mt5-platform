import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    // Allow browsing the Vite UI via the Windows EC2 public DNS / IP hostname.
    allowedHosts: [
      "ec2-13-201-137-73.ap-south-1.compute.amazonaws.com",
      ".ap-south-1.compute.amazonaws.com",
      "13.201.137.73",
    ],
  },
  build: {
    minify: "esbuild",
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
});

