import type { Metadata, Viewport } from "next";
import { Fraunces, Geist } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { Providers } from "@/components/providers";
import { Shell } from "@/components/shell/shell";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const fraunces = Fraunces({
  variable: "--font-fraunces",
  subsets: ["latin"],
  display: "swap",
  axes: ["opsz"],
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

export const metadata: Metadata = {
  title: "Pantry Cook",
  description: "Track your pantry and cook with what you have",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${geistSans.variable} ${fraunces.variable} h-full`} suppressHydrationWarning>
      <body className="h-full font-sans antialiased">
        <Script id="theme-boot" strategy="beforeInteractive">
          {`(function(){try{var d=document.documentElement;var c=localStorage.getItem('theme');if(c==='dark'||((!c||c==='system')&&window.matchMedia('(prefers-color-scheme:dark)').matches)){d.classList.add('dark')}}catch(e){}})()`}
        </Script>
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
