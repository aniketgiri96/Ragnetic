import "./globals.css";
import AppShell from "./components/AppShell";

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Just+Another+Hand&family=Space+Grotesk:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="min-h-screen flex flex-col overflow-x-hidden">
        <div className="fut-bg-orb fut-bg-orb-a" />
        <div className="fut-bg-orb fut-bg-orb-b" />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
