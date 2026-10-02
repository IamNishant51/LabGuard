import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LabGuard",
  description: "LabGuard college lab monitoring console (M1 shell)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <main>{children}</main>
      </body>
    </html>
  );
}
