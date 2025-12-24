import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Plattera",
  description: "Plattera helps teams align land data with speed and clarity.",
  icons: {
    icon: "/icon.ico",
    shortcut: "/icon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
