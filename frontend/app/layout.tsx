import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Site Scan — A clearer view of your website",
  description:
    "Understand your website’s performance, accessibility, and security with a single-page audit.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
