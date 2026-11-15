import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "B5 Research — Follow the evidence",
  description:
    "Explore the connections between biomarker profiles, research papers, clinical trials, and genomic models. Research prototype. Not medical advice.",
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
