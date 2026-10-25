import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'VarshaGuard Nebula Orb', description: 'NebulaOrb voice assistant visual for VarshaGuard.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) { return <html lang="en"><body>{children}</body></html>; }
