import { fileURLToPath, URL } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    // 5173/5174 는 Korail 쪽 moveai-carrier-ui·MOVEAI_AXIS2, 5273 은 Carrier_Portal 이 쓴다.
    port: 5175,
    strictPort: true,
    proxy: {
      // 로컬에서도 배포와 같은 경로(/api/*)로 호출한다.
      // `vercel dev` 를 띄우면 3000 번에서 api/ 함수가 실제로 실행된다.
      "/api": {
        target: process.env.VITE_API_TARGET ?? "http://127.0.0.1:3000",
        changeOrigin: true,
      },
    },
  },
});
