import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Paper Swing Bot",
  description: "Hosted paper swing bot — observe, pause, flatten. No buy button.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
